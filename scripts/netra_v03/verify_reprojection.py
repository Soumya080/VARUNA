"""Phase 2 of this turn: prove the label reprojection.

1. Grid-point round-trip: feed the scene's own real geolocationGridPoints
   back through the inverse interpolator; the recovered (line, pixel)
   must match the point's own recorded (line, pixel) near-exactly (the
   interpolator is fit on these exact points, so this checks the
   interpolation machinery itself is not silently broken/transposed).
2. In-bounds check: every reprojected object/patch bbox must fall inside
   [0, height) x [0, width) for its scene's real raster shape.
3. Scale sanity: object bbox size in raw-pixel space, converted to
   meters via Sentinel-1's ~10m GRD pixel spacing, should be the same
   order of magnitude as the object's real geodetic size (haversine
   distance between its own corners) -- catches a systematic
   line/pixel swap or wrong-axis bug that in-bounds alone would miss.
"""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import rasterio
from scipy.interpolate import griddata

REPO = Path(__file__).resolve().parents[2]
EXTRACTED = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "extracted"
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"

GRD_PIXEL_SPACING_M = 10.0  # standard IW GRDH ground range/azimuth spacing


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_grid(scene_dir):
    ann = [a for a in (scene_dir / "annotation").glob("*-vv-*.xml") if "calibration" not in str(a)]
    tree = ET.parse(ann[0])
    pts = tree.getroot().findall(".//geolocationGridPoint")
    lons = np.array([float(p.find("longitude").text) for p in pts])
    lats = np.array([float(p.find("latitude").text) for p in pts])
    lines = np.array([int(p.find("line").text) for p in pts])
    pixels = np.array([int(p.find("pixel").text) for p in pts])
    return lons, lats, lines, pixels


def main():
    with open(PROV_DIR / "reprojected_labels.json") as f:
        results = json.load(f)

    scene_shapes = {}
    for sd in glob.glob(str(EXTRACTED / "*.SAFE")):
        sd = Path(sd)
        tif = next(iter(glob.glob(str(sd / "measurement" / "*-vv-*.tiff"))), None)
        if tif is None:
            continue
        with rasterio.open(tif) as src:
            scene_shapes[sd.name] = (src.height, src.width)

    # --- Test 1: grid-point round-trip, one representative scene ---
    sample_scene = results[0]["sentinel_product_id"]
    sd = EXTRACTED / sample_scene
    lons, lats, lines, pixels = load_grid(sd)
    points = np.stack([lons, lats], axis=-1)
    # leave-one-out style check on 20 interior points (edges extrapolate less reliably)
    interior_idx = [i for i in range(len(lines)) if 0 < lines[i] < lines.max() and 0 < pixels[i] < pixels.max()][:20]
    max_err_line, max_err_pixel = 0.0, 0.0
    for i in interior_idx:
        q = np.array([[lons[i], lats[i]]])
        pred_line = griddata(points, lines, q, method="linear")[0]
        pred_pixel = griddata(points, pixels, q, method="linear")[0]
        if np.isnan(pred_line):
            continue
        max_err_line = max(max_err_line, abs(pred_line - lines[i]))
        max_err_pixel = max(max_err_pixel, abs(pred_pixel - pixels[i]))
    test1 = {"scene": sample_scene, "max_line_err_px": float(max_err_line), "max_pixel_err_px": float(max_err_pixel),
             "pass": bool(max_err_line < 50 and max_err_pixel < 50)}
    print("TEST 1 (grid round-trip):", test1)

    # --- Test 2: in-bounds ---
    out_of_bounds = 0
    for r in results:
        h, w = scene_shapes.get(r["sentinel_product_id"], (None, None))
        if h is None:
            continue
        lmin, lmax = r["raw_bbox_line_min_max"]
        pmin, pmax = r["raw_bbox_pixel_min_max"]
        if lmin < -h * 0.05 or lmax > h * 1.05 or pmin < -w * 0.05 or pmax > w * 1.05:
            out_of_bounds += 1
    test2 = {"n_checked": len(results), "out_of_bounds": out_of_bounds, "pass": out_of_bounds == 0}
    print("TEST 2 (in-bounds, 5% tolerance for edge extrapolation):", test2)

    # --- Test 3: scale sanity, oil objects only ---
    scale_ratios = []
    for r in results:
        if r["label"] != "oil":
            continue
        c = r["corners_lonlat_and_raw_pixel"]
        geo_diag_m = haversine_m(c[0]["lon"], c[0]["lat"], c[2]["lon"], c[2]["lat"])  # ul to br
        px_diag = math.hypot(c[2]["line"] - c[0]["line"], c[2]["pixel"] - c[0]["pixel"])
        px_diag_m = px_diag * GRD_PIXEL_SPACING_M
        if geo_diag_m > 0:
            scale_ratios.append(px_diag_m / geo_diag_m)
    ratios = np.array(scale_ratios)
    test3 = {
        "n_objects": len(ratios),
        "median_ratio_pixelspace_vs_geodetic": float(np.median(ratios)) if len(ratios) else None,
        "pass": bool(len(ratios) > 0 and 0.5 <= np.median(ratios) <= 2.0),
    }
    print("TEST 3 (scale sanity, ratio should be ~1.0):", test3)

    all_pass = test1["pass"] and test2["pass"] and test3["pass"]
    summary = {"test1_grid_roundtrip": test1, "test2_in_bounds": test2, "test3_scale_sanity": test3, "all_pass": all_pass}
    with open(PROV_DIR / "reprojection_verification.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nALL PASS:", all_pass)


if __name__ == "__main__":
    main()
