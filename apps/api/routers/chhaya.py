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

_MC20 = Path(__file__).resolve().parents[3] / "data" / "gold" / "events" / "mc20_v0_1"
_TILE_RECORDS = _MC20 / "sar" / "tile_records.json"
_TILE_DIR = _MC20 / "sar" / "tiles"
_AIS_JOIN = _MC20 / "ais" / "event_ais_join.json"


@lru_cache(maxsize=1)
def _tile_records() -> list[dict]:
    if not _TILE_RECORDS.exists():
        return []
    data = json.loads(_TILE_RECORDS.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else list(data.values())


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
def list_tiles():
    """Real MC20 Sentinel-1 tiles available for investigation."""
    recs = _tile_records()
    if not recs:
        return {"available": False,
                "reason": f"No MC20 tile records at {_TILE_RECORDS} — CHHAYA has no real SAR to read.",
                "tiles": []}
    return {
        "available": True,
        "scene_id": recs[0].get("parent_scene_id"),
        "sensor": recs[0].get("sensor"),
        "n_tiles": len(recs),
        "tiles": [{"tile_id": r["tile_id"], "bbox": r["bbox"],
                   "row": r.get("row"), "column": r.get("column")} for r in recs],
    }


@router.get("/investigate/{tile_id}")
def investigate(tile_id: str, threshold_sigma: float = 6.0):
    """Run the real CHHAYA v2 investigation over one real MC20 tile."""
    from varuna_chhaya.v2.detectors.cfar import CACFARDetector
    from varuna_chhaya.v2.service import ChhayaInvestigationV2

    recs = {r["tile_id"]: r for r in _tile_records()}
    rec = recs.get(tile_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown tile {tile_id!r}. Known: {sorted(recs)[:10]}")

    path = _TILE_DIR / f"{tile_id}.npy"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Tile array missing on disk: {path}")

    arr = np.load(path)
    vh = arr[0] if arr.ndim == 3 else arr
    vh = np.asarray(vh, dtype=np.float32)

    b = rec["bbox"]
    bbox = BBox(min_lon=b["min_lon"], min_lat=b["min_lat"],
                max_lon=b["max_lon"], max_lat=b["max_lat"])

    join = _ais_join()
    t_sar_raw = join.get("t_sar")
    t_sar = (datetime.fromisoformat(str(t_sar_raw).replace("Z", "+00:00"))
             if t_sar_raw else datetime.now().astimezone())
    ais_positions = _ais_points_for(bbox, t_sar)

    # ---- data-suitability check, reported honestly -------------------
    # These MC20 tiles were preprocessed for NETRA oil-slick SEGMENTATION:
    # normalised and clipped to [0,1]. That compression destroys the
    # amplitude dynamic range CA-CFAR needs — the brightest pixel in these
    # tiles sits ~3.5 sigma above the mean, so no threshold at or above 4
    # can physically fire, and dropping below that would return speckle,
    # not vessels. We say so instead of returning "no vessels" as though
    # the ocean were empty.
    peak_sigma = float((vh.max() - vh.mean()) / (vh.std() + 1e-9))
    looks_normalised = bool(vh.min() >= 0.0 and vh.max() <= 1.0001)
    suitability = None
    if looks_normalised and peak_sigma < threshold_sigma:
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
                "Raw (uncalibrated or sigma0) GRD amplitude is required."
            ),
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
