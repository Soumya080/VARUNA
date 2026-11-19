"""
VARUNA GRID — MC20 CHHAYA-V sigma0 tile builder (Phase 5A).

Re-derives the same 9 MC20 tile footprints as `build_mc20_event_gold.py`
(same SAFE product, same calibration LUTs, same geolocation, byte-identical
geometry via the shape-generic `tile_512`) but SKIPS
`apply_netra_normalization` entirely — that clip-to-[p2,p98]/scale-to-[0,1]
step is correct for NETRA's oil-slick SEGMENTATION model and destructive for
CA-CFAR VESSEL DETECTION, which needs the amplitude dynamic range the
normalization throws away (measured: normalized tiles peak 3.4-3.75 sigma
above the mean vs the 6.0 sigma CFAR threshold — physically unable to fire).

Output: data/gold/events/mc20_v0_1_sigma0/sar/ — a SIBLING directory, never
overwriting the NETRA-normalized v0_1 set. Both products remain independently
selectable via `?product=` on `/v1/chhaya/*`.

Honest framing, stated up front (do not lose this in a commit message):
the success criterion for this script is "CFAR is now physically CAPABLE of
firing on this product" (provable from the sigma-table
`validate_chhaya_sigma0.py` produces) — NOT "CFAR found a vessel". The 9
MC20 tiles may genuinely contain zero vessels; a truthful zero is a valid
outcome. Do not retune CACFARDetector's threshold_sigma to manufacture a
detection — it is a literature default, never tuned against VARUNA data.

Usage: python scripts/build_mc20_chhaya_sigma0.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from varuna_contracts.schemas import BBox  # noqa: E402
from varuna_data_eng.schemas.provenance import DataProvenance, PixelWindow, TileRecord  # noqa: E402
from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    parse_calibration_lut, tile_512,
)
import varuna_data_eng.preprocessing.sentinel1_grd_calibration as calmod  # noqa: E402

import json  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# ---------------------------------------------------------------------------
# Constants — identical MC20 case/window as build_mc20_event_gold.py, so
# tile geometry is byte-identical between the two products.
# ---------------------------------------------------------------------------
CASE_ID = "mc20_2023-01-15"
PRODUCT_VERSION = "mc20_v0_1_sigma0"
MC20_LAT, MC20_LON = 28.936, -88.970
T_SAR = datetime(2023, 1, 15, 0, 2, 6, 898000, tzinfo=UTC)
WINDOW = 1536

SAFE_DIR = (
    REPO_ROOT / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15"
    / "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE"
)

OUT_ROOT = REPO_ROOT / "data" / "gold" / "events" / PRODUCT_VERSION
EVENT_SPLIT = "mc20_event_inference"

# Fixed, explicit channel order for every tile this script writes. The
# router MUST index by this field, never by bare position 0/1 — that
# positional assumption is exactly M11 (docs/product/HONESTY_LEDGER.md #13):
# `apply_netra_normalization` returns [VV, VH] but the router treated index
# 0 as VH.
CHANNEL_ORDER = ["VV_db", "VH_db"]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def build_sar_sigma0() -> dict:
    if OUT_ROOT.exists() and any(OUT_ROOT.iterdir()):
        raise SystemExit(
            f"{OUT_ROOT} already exists and is non-empty — refusing to overwrite. "
            "A defect found later means a new version dir, never an in-place edit."
        )

    out_dir = OUT_ROOT / "sar"
    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    vv_ann = SAFE_DIR / "annotation" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
    vv_cal = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
    vh_cal = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
    vv_tiff = SAFE_DIR / "measurement" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.tiff"
    vh_tiff = SAFE_DIR / "measurement" / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.tiff"

    tree = ET.parse(vv_ann)
    grid_pts = tree.getroot().findall(".//geolocationGridPoint")
    all_lats = [float(p.find("latitude").text) for p in grid_pts]
    all_lons = [float(p.find("longitude").text) for p in grid_pts]
    scene_footprint = BBox(min_lon=min(all_lons), min_lat=min(all_lats),
                            max_lon=max(all_lons), max_lat=max(all_lats))

    def nearest_grid_point(target_line: int, target_pixel: int) -> tuple[float, float]:
        best, best_d2 = None, None
        for p in grid_pts:
            line, pixel = int(p.find("line").text), int(p.find("pixel").text)
            d2 = (line - target_line) ** 2 + (pixel - target_pixel) ** 2
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best = (float(p.find("latitude").text), float(p.find("longitude").text))
        return best

    anchor_best, anchor_d2 = None, None
    for p in grid_pts:
        lat, lon = float(p.find("latitude").text), float(p.find("longitude").text)
        d2 = (lat - MC20_LAT) ** 2 + (lon - MC20_LON) ** 2
        if anchor_d2 is None or d2 < anchor_d2:
            anchor_d2 = d2
            anchor_best = (int(p.find("line").text), int(p.find("pixel").text), lat, lon)
    line, pixel, grid_lat, grid_lon = anchor_best

    im = Image.open(vv_tiff)
    W, H = im.size
    half = WINDOW // 2
    left = max(0, min(pixel - half, W - WINDOW))
    top = max(0, min(line - half, H - WINDOW))

    def read_dn_window(tiff_path: Path) -> np.ndarray:
        im0 = Image.open(tiff_path)
        first_two = im0.tile[:2]
        base_offset = first_two[0].offset
        row_stride = first_two[1].offset - first_two[0].offset
        assert row_stride == W * 2
        out = np.empty((WINDOW, WINDOW), dtype=np.uint16)
        with open(tiff_path, "rb") as f:
            for i, row in enumerate(range(top, top + WINDOW)):
                f.seek(base_offset + row * row_stride + left * 2)
                out[i] = np.frombuffer(f.read(WINDOW * 2), dtype="<u2")
        return out

    vv_dn = read_dn_window(vv_tiff)
    vh_dn = read_dn_window(vh_tiff)

    def calibrate_window(dn_window: np.ndarray, cal_xml: Path) -> np.ndarray:
        lut = parse_calibration_lut(cal_xml)
        shifted_lut = replace(lut, lines=lut.lines - top, pixels=lut.pixels - left)
        sigma_grid = calmod._interpolate_lut_to_grid(shifted_lut, dn_window.shape[0], dn_window.shape[1])
        with np.errstate(divide="ignore", invalid="ignore"):
            sigma0_linear = (dn_window.astype(np.float64) ** 2) / (sigma_grid ** 2)
            db = 10.0 * np.log10(sigma0_linear)
        return np.where(dn_window == 0, np.nan, db).astype(np.float32)

    vv_db = calibrate_window(vv_dn, vv_cal)
    vh_db = calibrate_window(vh_dn, vh_cal)

    # THE fix: no apply_netra_normalization call. Raw calibrated sigma0 dB,
    # stacked in the fixed CHANNEL_ORDER (VV, VH) so tile_512 (shape-generic)
    # produces byte-identical tile geometry to the NETRA gold set.
    stacked = np.stack([vv_db, vh_db], axis=0)  # [2, H, W], matches CHANNEL_ORDER
    tiles = tile_512(stacked, scene_id=CASE_ID)

    tile_records = []
    for t in tiles:
        tile_path = tiles_dir / f"{t.tile_id}.npy"
        np.save(tile_path, t.array)

        # Explicit valid_mask: True where NEITHER channel is NaN (DN==0
        # no-data). CFAR must respect this so a no-data edge is never
        # reported as a vessel — see CACFARDetector's own nan-handling.
        valid_mask = ~(np.isnan(t.array[0]) | np.isnan(t.array[1]))
        mask_path = tiles_dir / f"{t.tile_id}__valid_mask.npy"
        np.save(mask_path, valid_mask)

        r0, c0 = top + t.row, left + t.col
        r1, c1 = r0 + 512, c0 + 512
        corners = [nearest_grid_point(r0, c0), nearest_grid_point(r0, c1),
                   nearest_grid_point(r1, c0), nearest_grid_point(r1, c1)]
        lats = [c[0] for c in corners]
        lons = [c[1] for c in corners]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        deg_per_px_lon = (scene_footprint.max_lon - scene_footprint.min_lon) / W
        deg_per_px_lat = (scene_footprint.max_lat - scene_footprint.min_lat) / H
        eps_lon, eps_lat = 256 * deg_per_px_lon, 256 * deg_per_px_lat
        bbox_padded = False
        if min_lon >= max_lon:
            min_lon, max_lon = min_lon - eps_lon, max_lon + eps_lon
            bbox_padded = True
        if min_lat >= max_lat:
            min_lat, max_lat = min_lat - eps_lat, max_lat + eps_lat
            bbox_padded = True
        tile_bbox = BBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)

        rec = TileRecord(
            tile_id=t.tile_id,
            parent_scene_id=CASE_ID,
            split=EVENT_SPLIT,
            sensor="Sentinel-1A_IW_GRDH",
            source="sentinel1_grd_mc20_sigma0",
            row=t.row, column=t.col,
            pixel_window=PixelWindow(x_offset=c0, y_offset=r0, width=512, height=512),
            bbox=tile_bbox,
            provenance=DataProvenance(
                source_id="sentinel1_grd_mc20",
                adapter_id="scripts.build_mc20_chhaya_sigma0",
                license="Copernicus Sentinel Data Terms and Conditions (free, open)",
                raw_artifact_path=str(SAFE_DIR),
                notes=(
                    "calibrated sigma0 dB via sentinel1_grd_calibration.py (real, unmodified); "
                    "NOT normalized — apply_netra_normalization deliberately skipped so CA-CFAR "
                    "retains the amplitude dynamic range vessel detection needs "
                    "(see this script's own module docstring); "
                    "tile bbox is an approximation from the nearest of 210 sparse "
                    "geolocationGrid points, not exact bilinear interpolation"
                    + ("; bbox corners collapsed to a single grid point — padded by half the "
                       "tile's approximate angular footprint" if bbox_padded else "")
                ),
            ),
        )
        # extra keys beyond TileRecord's own extra="forbid" schema — added
        # to the DICT after serialization, since the router reads these as
        # plain JSON, not a re-validated TileRecord.
        rec_dict = json.loads(rec.model_dump_json())
        rec_dict["product"] = PRODUCT_VERSION
        rec_dict["channel_order"] = CHANNEL_ORDER
        rec_dict["units"] = "dB (sigma0, calibrated, uncorrected for terrain/thermal-noise)"
        rec_dict["normalization"] = None
        rec_dict["valid_mask_path"] = str(mask_path)
        tile_records.append(rec_dict)

    tile_records_path = out_dir / "tile_records.json"
    tile_records_path.write_text(json.dumps(tile_records, indent=2))

    summary = {
        "product": PRODUCT_VERSION,
        "safe_dir": str(SAFE_DIR),
        "acquisition_timestamp": T_SAR.isoformat(),
        "scene_footprint": json.loads(scene_footprint.model_dump_json()),
        "anchor_geolocation_lookup": {
            "line": line, "pixel": pixel, "lat": grid_lat, "lon": grid_lon,
            "distance_from_exact_anchor_km": _haversine_km(MC20_LAT, MC20_LON, grid_lat, grid_lon),
        },
        "crop_window_px": {"top": top, "left": left, "size": WINDOW},
        "n_tiles": len(tiles),
        "tile_dir": str(tiles_dir),
        "tile_records_path": str(tile_records_path),
        "channel_order": CHANNEL_ORDER,
        "units": "dB",
        "normalization": None,
        "vv_db_range": [float(np.nanmin(vv_db)), float(np.nanmax(vv_db))],
        "vh_db_range": [float(np.nanmin(vh_db)), float(np.nanmax(vh_db))],
        "thermal_noise_removed": False,
        "terrain_correction_applied": False,
        "speckle_filter_applied": False,
    }
    summary_path = out_dir / "build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    summary = build_sar_sigma0()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
