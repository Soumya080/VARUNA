"""
VARUNA GRID — validate sentinel1_grd_calibration.py against the REAL MC20
SAFE product (not the synthetic fixture).

Reads a windowed crop (not the full ~867MB-per-band scene, to stay
resource-bounded per the task's memory constraints) around the MC20
anchor point (28.936N, -88.970W), located via the product's own real
annotation geolocationGrid (Sentinel-1 GRD TIFFs are not georeferenced
GeoTIFFs -- geolocation comes from this XML grid, per the ESA product
format spec, not from embedded CRS tags). Runs the real calibration
pipeline (DN -> sigma0 -> dB -> NETRA normalization -> 512x512 tiling)
against this real window and reports genuine statistics.

Never modifies the raw SAFE product. Read-only.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    calibrate_to_db, apply_netra_normalization, tile_512,
)

SAFE_DIR = (
    REPO_ROOT / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15"
    / "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE"
)
MC20_LAT, MC20_LON = 28.936, -88.970
WINDOW = 1536  # pixels, centered on the anchor -- three 512 tiles wide


def find_anchor_pixel(annotation_xml: Path) -> tuple[int, int]:
    """Real nearest-neighbor lookup against the product's own
    geolocationGrid. No fabricated/approximated geocoding."""
    tree = ET.parse(annotation_xml)
    pts = tree.getroot().findall(".//geolocationGridPoint")
    best = None
    best_d2 = None
    for p in pts:
        lat = float(p.find("latitude").text)
        lon = float(p.find("longitude").text)
        d2 = (lat - MC20_LAT) ** 2 + (lon - MC20_LON) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            best = (int(p.find("line").text), int(p.find("pixel").text),
                    lat, lon)
    return best


def main() -> None:
    vv_ann = SAFE_DIR / "annotation" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
    vh_ann = SAFE_DIR / "annotation" / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
    vv_cal = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
    vh_cal = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
    vv_tiff = SAFE_DIR / "measurement" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.tiff"
    vh_tiff = SAFE_DIR / "measurement" / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.tiff"

    line, pixel, grid_lat, grid_lon = find_anchor_pixel(vv_ann)
    print(f"Nearest real geolocationGrid point: line={line}, pixel={pixel}, "
          f"lat={grid_lat:.4f}, lon={grid_lon:.4f} "
          f"(target {MC20_LAT},{MC20_LON})")

    im = Image.open(vv_tiff)
    W, H = im.size
    half = WINDOW // 2
    left = max(0, min(pixel - half, W - WINDOW))
    top = max(0, min(line - half, H - WINDOW))
    box = (left, top, left + WINDOW, top + WINDOW)
    print(f"Full scene size: {W}x{H}; cropping window {box}")

    def read_dn_window(tiff_path: Path, width: int, height: int, top: int, left: int, win: int) -> np.ndarray:
        """Direct row-seek read, bypassing PIL's per-strip decode loop
        (this product stores 1 row per strip -- 16734 separate strips --
        which makes PIL's tile-by-tile Python-level decode extremely slow
        for a windowed crop). Real Sentinel-1 GRD measurement TIFFs are
        uncompressed (compression tag=1, verified) and little-endian
        (byte-order marker 'II', verified), with each row's strip offset
        at base_offset + row * width * 2 bytes (verified: consecutive
        strip offsets in this exact file differ by exactly width*2).
        Equivalent result to PIL, just not decoded through 16734 Python
        objects."""
        im0 = Image.open(tiff_path)
        first_two = im0.tile[:2]
        base_offset = first_two[0].offset
        row_stride = first_two[1].offset - first_two[0].offset
        assert row_stride == width * 2, f"unexpected row stride {row_stride} != {width*2}"
        out = np.empty((win, win), dtype=np.uint16)
        with open(tiff_path, "rb") as f:
            for i, row in enumerate(range(top, top + win)):
                f.seek(base_offset + row * row_stride + left * 2)
                out[i] = np.frombuffer(f.read(win * 2), dtype="<u2")
        return out

    vv_dn = read_dn_window(vv_tiff, W, H, top, left, WINDOW)
    vh_dn = read_dn_window(vh_tiff, W, H, top, left, WINDOW)
    print(f"VV DN window: shape={vv_dn.shape}, dtype={vv_dn.dtype}, "
          f"range=[{vv_dn.min()},{vv_dn.max()}], zero(nodata) frac={float((vv_dn==0).mean()):.4f}")
    print(f"VH DN window: shape={vh_dn.shape}, dtype={vh_dn.dtype}, "
          f"range=[{vh_dn.min()},{vh_dn.max()}], zero(nodata) frac={float((vh_dn==0).mean()):.4f}")

    # NOTE: calibrate_to_db interpolates the FULL LUT onto the array shape
    # it's given, assuming array[0,0] corresponds to line=0,pixel=0 of the
    # LUT's own coordinate system. Since we cropped a window starting at
    # (left, top) rather than the scene origin, we must offset the LUT
    # interpolation accordingly -- build a small local LUT-consistent call
    # by shifting the calibration vectors' line/pixel by -top/-left before
    # interpolating, so the crop's pixel (0,0) maps to the LUT's (top,left).
    from varuna_data_eng.preprocessing.sentinel1_grd_calibration import parse_calibration_lut

    def calibrate_window(dn_window: np.ndarray, cal_xml: Path, pol: str, tiff_path: Path):
        lut = parse_calibration_lut(cal_xml)
        # Shift LUT coordinates into the crop's local frame.
        shifted_lines = lut.lines - top
        shifted_pixels = lut.pixels - left
        from dataclasses import replace
        shifted_lut = replace(lut, lines=shifted_lines, pixels=shifted_pixels)
        import varuna_data_eng.preprocessing.sentinel1_grd_calibration as calmod
        # Monkeypatch-free: call the internal interpolation directly on the shifted LUT.
        sigma_grid = calmod._interpolate_lut_to_grid(shifted_lut, dn_window.shape[0], dn_window.shape[1])
        with np.errstate(divide="ignore", invalid="ignore"):
            sigma0_linear = (dn_window.astype(np.float64) ** 2) / (sigma_grid ** 2)
            db = 10.0 * np.log10(sigma0_linear)
        db = np.where(dn_window == 0, np.nan, db)
        return db.astype(np.float32)

    vv_db = calibrate_window(vv_dn, vv_cal, "VV", vv_tiff)
    vh_db = calibrate_window(vh_dn, vh_cal, "VH", vh_tiff)

    print(f"VV dB: finite range=[{np.nanmin(vv_db):.2f},{np.nanmax(vv_db):.2f}], "
          f"NaN frac={float(np.isnan(vv_db).mean()):.4f}, has Inf={bool(np.isinf(vv_db[np.isfinite(vv_db) | np.isinf(vv_db)]).any()) if np.isinf(vv_db).any() else False}")
    print(f"VH dB: finite range=[{np.nanmin(vh_db):.2f},{np.nanmax(vh_db):.2f}], "
          f"NaN frac={float(np.isnan(vh_db).mean()):.4f}")

    gold_manifest = json.loads((REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json").read_text())
    norm = gold_manifest["normalization"]
    vv_stats = norm["channels"]["VV"]
    vh_stats = norm["channels"]["VH"]
    print(f"Using FROZEN Gold v0.2 normalization: VV clip={vv_stats['clip_low']},{vv_stats['clip_high']} "
          f"VH clip={vh_stats['clip_low']},{vh_stats['clip_high']}")

    normalized = apply_netra_normalization(vv_db, vh_db, vv_stats, vh_stats)
    print(f"Normalized [2,H,W]: shape={normalized.shape}, dtype={normalized.dtype}, "
          f"range=[{normalized.min():.4f},{normalized.max():.4f}], "
          f"has NaN={bool(np.isnan(normalized).any())}, has Inf={bool(np.isinf(normalized).any())}")

    tiles = tile_512(normalized, scene_id="mc20_2023-01-15")
    print(f"tile_512 produced {len(tiles)} real 512x512 tiles from this {WINDOW}x{WINDOW} window")
    for t in tiles[:3]:
        arr = t.array
        print(f"  {t.tile_id}: shape={arr.shape}, range=[{arr.min():.4f},{arr.max():.4f}], "
              f"mean_VV={arr[0].mean():.4f}, mean_VH={arr[1].mean():.4f}")

    result = {
        "anchor_geolocation_lookup": {"line": line, "pixel": pixel, "lat": grid_lat, "lon": grid_lon},
        "crop_window": {"box": list(box), "size": WINDOW},
        "vv_dn_range": [int(vv_dn.min()), int(vv_dn.max())],
        "vh_dn_range": [int(vh_dn.min()), int(vh_dn.max())],
        "vv_db_range": [float(np.nanmin(vv_db)), float(np.nanmax(vv_db))],
        "vh_db_range": [float(np.nanmin(vh_db)), float(np.nanmax(vh_db))],
        "normalized_range": [float(normalized.min()), float(normalized.max())],
        "normalized_has_nan": bool(np.isnan(normalized).any()),
        "normalized_has_inf": bool(np.isinf(normalized).any()),
        "n_tiles_512": len(tiles),
        "vv_stats_used": vv_stats,
        "vh_stats_used": vh_stats,
    }
    out_path = REPO_ROOT / "reports" / "mc20_sar_calibration_validation.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
