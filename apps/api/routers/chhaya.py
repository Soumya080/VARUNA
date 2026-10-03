"""
VARUNA — CHHAYA v2 vessel intelligence endpoint (Workstream B wiring).

Runs the REAL CHHAYA v2 investigation over REAL MC20 Sentinel-1 GRD tiles
and REAL AIS positions from `data/gold/events/mc20_v0_1`. Nothing here
synthesises SAR imagery or vessel positions.

Detector choice, stated honestly: the xView3 Faster-RCNN checkpoint requires
a third `bathymetry` input channel (see
reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md — confirmed by inspecting
`conv1` in the published weights), and no bathymetry raster exists for this
event. CHHAYA therefore runs the classical CA-CFAR detector, which is a real
detector operating on real imagery — not a stand-in for one. The response
always names which detector ran via `detector_source`/`detector_mode`, so a
reader can never mistake CFAR output for a learned model's.
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException

from varuna_contracts.schemas import AISPoint, BBox

router = APIRouter(prefix="/v1/chhaya", tags=["chhaya"])

_EVENTS_DIR = Path(__file__).resolve().parents[3] / "data" / "gold" / "events"
_MC20 = _EVENTS_DIR / "mc20_v0_1"
_TILE_RECORDS = _MC20 / "sar" / "tile_records.json"
_TILE_DIR = _MC20 / "sar" / "tiles"
_AIS_JOIN = _MC20 / "ais" / "event_ais_join.json"

# Phase 5A (docs/product/HONESTY_LEDGER.md): the `netra_normalized` product
# is `apply_netra_normalization`'s [p2,p98]-clipped/[0,1]-scaled output,
# whose real return order is `[VV_norm, VH_norm]` (see that function's own
# docstring) — this is M11's root cause: earlier code assumed index 0 was
# VH. `sigma0` is the new raw-calibrated-dB product from
# `scripts/build_mc20_chhaya_sigma0.py`, deliberately never normalized so
# CFAR keeps the amplitude range it needs. Both carry an explicit
# `channel_order` per tile record (see `_channel_index` below) — index-by-
# NAME, never bare position, is the actual fix.
_PRODUCTS = {
    "netra_normalized": {
        "dir": _MC20,
        "default_channel_order": ["VV_norm", "VH_norm"],
    },
    "sigma0": {
        "dir": _EVENTS_DIR / "mc20_v0_1_sigma0",
        "default_channel_order": ["VV_db", "VH_db"],
    },
}


@lru_cache(maxsize=8)
def _tile_records(product: str = "netra_normalized") -> list[dict]:
    base = _PRODUCTS.get(product, _PRODUCTS["netra_normalized"])["dir"]
    tile_records_path = base / "sar" / "tile_records.json"
    if not tile_records_path.exists():
        return []
    data = json.loads(tile_records_path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else list(data.values())


def _tile_dir(product: str = "netra_normalized") -> Path:
    return _PRODUCTS.get(product, _PRODUCTS["netra_normalized"])["dir"] / "sar" / "tiles"


def _channel_index(rec: dict, product: str, name: str) -> int:
    """Index a tile's channel array by NAME (e.g. "VH"), never bare
    position — the actual M11 fix. `channel_order` on the record wins when
    present (every `sigma0` tile has it); the `netra_normalized` product's
    older records predate that field, so fall back to the product's known,
    verified real order (`apply_netra_normalization`'s docstring)."""
    order = rec.get("channel_order") or _PRODUCTS.get(product, {}).get("default_channel_order")
    if not order:
        raise HTTPException(500, f"no channel_order known for product {product!r}")
    for i, ch in enumerate(order):
        if name in ch:
            return i
    raise HTTPException(500, f"channel {name!r} not found in channel_order {order}")


@lru_cache(maxsize=1)
def _ais_join() -> dict:
    if not _AIS_JOIN.exists():
        return {}
    return json.loads(_AIS_JOIN.read_text(encoding="utf-8"))


def _ais_points_for(bbox: BBox, t_sar: datetime) -> list[AISPoint]:
    """Real AIS positions from the MC20 join, filtered to the tile footprint.

    Returns [] when the join carries no per-position payload — which the
    downstream `classify_outcome()` correctly reads as insufficient AIS
    coverage rather than as evidence of a dark vessel.
    """
    join = _ais_join()
    pts: list[AISPoint] = []
    tracks = join.get("tracks") or join.get("matched_tracks") or []
    for tr in tracks if isinstance(tracks, list) else []:
        for p in (tr.get("points") or []):
            lon, lat = p.get("lon"), p.get("lat")
            if lon is None or lat is None:
                continue
            if not (bbox.min_lon <= lon <= bbox.max_lon and bbox.min_lat <= lat <= bbox.max_lat):
                continue
            try:
                pts.append(AISPoint(
                    timestamp=datetime.fromisoformat(str(p["timestamp"]).replace("Z", "+00:00")),
                    lon=float(lon), lat=float(lat),
                    sog_knots=p.get("sog_knots"), cog_deg=p.get("cog_deg"),
                ))
            except Exception:
                continue
    return pts


@router.get("/tiles")
def list_tiles(product: str = "netra_normalized"):
    """Real MC20 Sentinel-1 tiles available for investigation.

    `product`: `netra_normalized` (the original [0,1]-scaled tiles, the
    NETRA segmentation model's actual input) or `sigma0` (Phase 5A's raw
    calibrated-dB tiles, physically capable of a wider CFAR dynamic range —
    see `scripts/build_mc20_chhaya_sigma0.py`).
    """
    recs = _tile_records(product)
    if not recs:
        return {"available": False,
                "product": product,
                "reason": f"No MC20 tile records for product {product!r} at "
                          f"{_tile_dir(product).parent / 'tile_records.json'} — "
                          "CHHAYA has no real SAR to read for this product.",
                "tiles": []}
    return {
        "available": True,
        "product": product,
        "scene_id": recs[0].get("parent_scene_id"),
        "sensor": recs[0].get("sensor"),
        "n_tiles": len(recs),
        "tiles": [{"tile_id": r["tile_id"], "bbox": r["bbox"],
                   "row": r.get("row"), "column": r.get("column")} for r in recs],
    }


@router.get("/investigate/{tile_id}")
def investigate(tile_id: str, threshold_sigma: float = 6.0, product: str = "netra_normalized"):
    """Run the real CHHAYA v2 investigation over one real MC20 tile.

    `product` selects which tile product to run against — see `/tiles`'s
    own docstring. Defaults to `netra_normalized` for backward
    compatibility with existing callers.
    """
    from varuna_chhaya.v2.detectors.cfar import CACFARDetector
    from varuna_chhaya.v2.service import ChhayaInvestigationV2

    recs = {r["tile_id"]: r for r in _tile_records(product)}
    rec = recs.get(tile_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown tile {tile_id!r} for product {product!r}. Known: {sorted(recs)[:10]}")

    path = _tile_dir(product) / f"{tile_id}.npy"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Tile array missing on disk: {path}")

    arr = np.load(path)
    # M11 fix (docs/product/HONESTY_LEDGER.md #13): index by NAME via
    # `channel_order`, never bare position — `arr[0]` was VV, not VH.
    vh_idx = _channel_index(rec, product, "VH") if arr.ndim == 3 else 0
    vh = arr[vh_idx] if arr.ndim == 3 else arr
    vh = np.asarray(vh, dtype=np.float32)

    # Phase 5A domain fix: `CACFARDetector.detect()` assumes non-negative
    # LINEAR amplitude (`np.clip(x, 0.0, None)`) — correct for the
    # `netra_normalized` product ([0,1]-scaled) but wrong for `sigma0`,
    # whose values are calibrated dB (legitimately negative for most of a
    # sea surface, e.g. this event's real VH range is -49 to +4 dB).
    # Feeding dB straight into a clip-at-zero detector would zero out
    # nearly the entire scene. Convert back to linear power
    # (sigma0_db = 10*log10(sigma0_linear) was the original calibration
    # step — this is its exact inverse, not an approximation) before
    # detection; a no-data pixel's valid_mask (built alongside the sigma0
    # tiles) is applied as an explicit 0 rather than a NaN the detector
    # would otherwise silently zero anyway, so a no-data edge can never be
    # mistaken for a bright target.
    is_db_product = "db" in str(rec.get("units", "")).lower()
    if is_db_product:
        valid_mask_path = rec.get("valid_mask_path")
        valid = None
        if valid_mask_path and Path(valid_mask_path).exists():
            valid = np.load(valid_mask_path)
        vh_linear = np.power(10.0, np.nan_to_num(vh, nan=-100.0) / 10.0)
        if valid is not None:
            vh_linear = np.where(valid, vh_linear, 0.0)
        vh = vh_linear.astype(np.float32)

    b = rec["bbox"]
    bbox = BBox(min_lon=b["min_lon"], min_lat=b["min_lat"],
                max_lon=b["max_lon"], max_lat=b["max_lat"])

    join = _ais_join()
    t_sar_raw = join.get("t_sar")
    t_sar = (datetime.fromisoformat(str(t_sar_raw).replace("Z", "+00:00"))
             if t_sar_raw else datetime.now().astimezone())
    ais_positions = _ais_points_for(bbox, t_sar)

    # ---- data-suitability check, reported honestly -------------------
    # Phase 5A: `product` now tells us directly which preprocessing this
    # tile went through — no need to guess from the value range (which
    # became unreliable once `sigma0` values are converted to linear power
    # above; a quiet tile's linear amplitude can coincidentally also sit in
    # [0,1]). `netra_normalized` tiles are clipped to [0,1] for NETRA
    # oil-slick SEGMENTATION, which destroys the amplitude dynamic range
    # CA-CFAR needs; `sigma0` tiles are the Phase 5A raw-calibrated product
    # built specifically to avoid that.
    peak_sigma = float((vh.max() - vh.mean()) / (vh.std() + 1e-9))
    is_normalized_product = product == "netra_normalized"
    suitability = None
    if is_normalized_product and peak_sigma < threshold_sigma:
        suitability = {
            "suitable_for_cfar": False,
            "peak_sigma_above_mean": round(peak_sigma, 2),
            "threshold_sigma": threshold_sigma,
            "reason": (
                "This tile is normalised/clipped to [0,1] (NETRA oil-slick segmentation "
                f"preprocessing). Its brightest pixel is only {peak_sigma:.1f} sigma above the "
                f"mean, below the {threshold_sigma} sigma CFAR threshold, so vessel detection "
                "cannot fire on this product. A NO_SUPPORTED_VESSEL outcome here means "
                "'this imagery cannot support vessel detection', NOT 'no vessels are present'. "
                "Try ?product=sigma0 for the raw-calibrated alternative "
                "(reports/chhaya_v2/CHHAYA_SIGMA0_SUITABILITY_REPORT.md)."
            ),
        }
    elif not is_normalized_product and peak_sigma < threshold_sigma:
        suitability = {
            "suitable_for_cfar": False,
            "peak_sigma_above_mean": round(peak_sigma, 2),
            "threshold_sigma": threshold_sigma,
            "reason": (
                f"Raw-calibrated sigma0 product, physically capable of a wider dynamic "
                f"range than netra_normalized — but this specific tile's brightest pixel "
                f"is still only {peak_sigma:.1f} sigma above the mean, below the "
                f"{threshold_sigma} sigma threshold. A truthful zero: this tile may "
                "genuinely contain no vessel, not a preprocessing artifact."
            ),
        }
    elif not is_normalized_product:
        suitability = {
            "suitable_for_cfar": True,
            "peak_sigma_above_mean": round(peak_sigma, 2),
            "threshold_sigma": threshold_sigma,
            "reason": "Raw-calibrated sigma0 product; peak signal clears the CFAR threshold.",
        }

    svc = ChhayaInvestigationV2(detector=CACFARDetector(threshold_sigma=threshold_sigma))
    handoff = svc.investigate(
        case_id=f"MC20-{tile_id}",
        scene_id=rec.get("parent_scene_id", "mc20"),
        source_artifact_id=str(path),
        vh=vh,
        acquisition_time=t_sar,
        scene_bbox=bbox,
        ais_positions=ais_positions,
    )

    payload = (handoff.model_dump(mode="json") if hasattr(handoff, "model_dump")
               else json.loads(json.dumps(handoff, default=str)))

    # Phase 5B (docs/product/HONESTY_LEDGER.md): `chhaya_bridge.py` existed,
    # complete and tested, and was never called from any route — the
    # CHHAYA-V -> NYAYA handoff it implements was real but invisible.
    # Surfaced here as `dark_contact_evidence`: a small, bounded, explicitly
    # NOT-a-posterior prior nudge (see the module's own docstring for why
    # it must never become a decision by itself).
    from varuna_nyaya.chhaya_bridge import dark_contact_prior_contribution
    dark_contact = dark_contact_prior_contribution(handoff)
    payload["dark_contact_evidence"] = {
        "supported": dark_contact.supported,
        "top_candidate_plausibility": dark_contact.top_candidate_plausibility,
        "prior_nudge": dark_contact.prior_nudge,
        "explanation": dark_contact.explanation,
    }

    payload["_input"] = {
        "tile_id": tile_id,
        "tile_shape": list(vh.shape),
        "tile_bbox": rec["bbox"],
        "sensor": rec.get("sensor"),
        "n_ais_positions_in_tile": len(ais_positions),
        # Real positions, not just the count (Phase 1) — already computed
        # above by _ais_points_for(), the frontend just never received them.
        "ais_positions": [{"lon": p.lon, "lat": p.lat} for p in ais_positions],
        "ais_source": str(_AIS_JOIN) if _AIS_JOIN.exists() else None,
        "sar_source": str(path),
        "suitability": suitability,
        "corridor_recurrence": _corridor_recurrence(bbox),
        "detector_note": (
            "CA-CFAR (classical) on real Sentinel-1 GRD. xView3 Faster-RCNN is NOT used: "
            "its published checkpoint requires a bathymetry input channel that does not "
            "exist for this event — see reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md."
        ),
    }
    return payload


_CORRIDOR_RADIUS_KM = 50.0


def _corridor_recurrence(bbox: BBox) -> dict:
    """Real SMRITI recurrence count for this tile's centroid (Phase 1) — a
    genuine, if simple, count of prior remembered cases nearby, not an
    estimate. See packages/varuna_smriti/memory.py::corridor_case_count(),
    whose own docstring already says it feeds CHHAYA's recurrence factor;
    this endpoint was the first caller to actually use it."""
    from apps.api.dependencies import get_replay_smriti_store

    lon = (bbox.min_lon + bbox.max_lon) / 2.0
    lat = (bbox.min_lat + bbox.max_lat) / 2.0
    store = get_replay_smriti_store()
    count = store.corridor_case_count(lon, lat, _CORRIDOR_RADIUS_KM)
    return {"count": count, "radius_km": _CORRIDOR_RADIUS_KM}
