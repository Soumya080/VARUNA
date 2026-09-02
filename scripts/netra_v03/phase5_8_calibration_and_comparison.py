"""Phase 5 (re-verify VV/VH per scene) + Phase 8 (compare ESSD/PANGAEA GRD
scenes against NETRA-GOLD-v0.2's already-established per-channel
statistics), computed on real calibrated Sigma0 dB, not raw DN.

Downsampled (not full-resolution) for tractability across 25 scenes x
2 polarizations x ~25000x16700px each -- this is a distribution-coverage
check, not a training input, so a large deterministic subsample is
appropriate (same class of method as the Smart-Fix 400-tile coverage
check).
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import rasterio
from scipy.interpolate import RegularGridInterpolator

REPO = Path(__file__).resolve().parents[2]
EXTRACTED = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "extracted"
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"

DOWNSAMPLE = 20  # every 20th pixel in each axis -> ~1250x830 per scene

# NETRA-GOLD-v0.2 reference ranges, from data/manifests/netra_gold_v0_2.json
V02_CLIP = {
    "VV": (-42.475, -13.825),
    "VH": (-33.425, -7.525),
}


def parse_lut(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    vectors = root.findall(".//calibrationVector")
    lines, pixels_list, sigma_list = [], [], []
    for vec in vectors:
        lines.append(int(vec.find("line").text))
        pixels_list.append(np.array([int(p) for p in vec.find("pixel").text.split()]))
        sigma_list.append(np.array([float(s) for s in vec.find("sigmaNought").text.split()]))
    return np.array(lines), np.stack(pixels_list), np.stack(sigma_list)


def calibrate_downsampled(tiff_path, calib_xml_path, downsample=DOWNSAMPLE):
    with rasterio.open(tiff_path) as src:
        h, w = src.height, src.width
        out_h, out_w = h // downsample, w // downsample
        dn = src.read(1, out_shape=(1, out_h, out_w)).astype(np.float64)

    lines, pixels, sigma = parse_lut(calib_xml_path)
    pixel_axis = pixels[0]
    interp = RegularGridInterpolator((lines, pixel_axis), sigma, bounds_error=False, fill_value=None)

    line_idx = np.linspace(0, h - 1, out_h)
    pixel_idx = np.linspace(0, w - 1, out_w)
    line_grid, pixel_grid = np.meshgrid(line_idx, pixel_idx, indexing="ij")
    sigma_grid = interp(np.stack([line_grid.ravel(), pixel_grid.ravel()], axis=-1)).reshape(out_h, out_w)

    with np.errstate(divide="ignore", invalid="ignore"):
        sigma0_linear = (dn ** 2) / (sigma_grid ** 2)
        db = 10.0 * np.log10(sigma0_linear)
    db = np.where(dn == 0, np.nan, db)
    return db.astype(np.float32)


def main():
    scene_dirs = sorted(glob.glob(str(EXTRACTED / "*.SAFE")))
    print(f"{len(scene_dirs)} scenes")

    per_scene = []
    for sd in scene_dirs:
        sd = Path(sd)
        name = sd.name
        meas_dir = sd / "measurement"
        calib_dir = sd / "annotation" / "calibration"
        vv_tiff = next(iter(glob.glob(str(meas_dir / "*-vv-*.tiff"))), None)
        vh_tiff = next(iter(glob.glob(str(meas_dir / "*-vh-*.tiff"))), None)
        vv_cal = next(iter(glob.glob(str(calib_dir / "calibration-*-vv-*.xml"))), None)
        vh_cal = next(iter(glob.glob(str(calib_dir / "calibration-*-vh-*.xml"))), None)
        if not all([vv_tiff, vh_tiff, vv_cal, vh_cal]):
            print(f"[skip] {name}: missing measurement/calibration files")
            continue

        vv_db = calibrate_downsampled(vv_tiff, vv_cal)
        vh_db = calibrate_downsampled(vh_tiff, vh_cal)

        vv_valid = vv_db[np.isfinite(vv_db)]
        vh_valid = vh_db[np.isfinite(vh_db)]

        entry = {
            "scene": name,
            "vv_mean_db": float(np.mean(vv_valid)),
            "vv_p1_db": float(np.percentile(vv_valid, 1)),
            "vv_p99_db": float(np.percentile(vv_valid, 99)),
            "vh_mean_db": float(np.mean(vh_valid)),
            "vh_p1_db": float(np.percentile(vh_valid, 1)),
            "vh_p99_db": float(np.percentile(vh_valid, 99)),
            "vv_brighter_than_vh": bool(np.mean(vv_valid) > np.mean(vh_valid)),
            "valid_fraction_vv": float(vv_valid.size / vv_db.size),
            "valid_fraction_vh": float(vh_valid.size / vh_db.size),
        }
        per_scene.append(entry)
        print(f"{name[:40]}: VV={entry['vv_mean_db']:.2f}dB VH={entry['vh_mean_db']:.2f}dB "
              f"VVbrighter={entry['vv_brighter_than_vh']}")

    with open(PROV_DIR / "phase5_8_per_scene_calibration.json", "w") as f:
        json.dump(per_scene, f, indent=2)

    n_ok = sum(1 for e in per_scene if e["vv_brighter_than_vh"])
    print(f"\nVV brighter than VH: {n_ok}/{len(per_scene)} scenes (physical sanity check)")

    vv_means = [e["vv_mean_db"] for e in per_scene]
    vh_means = [e["vh_mean_db"] for e in per_scene]
    vv_lo, vv_hi = V02_CLIP["VV"]
    vh_lo, vh_hi = V02_CLIP["VH"]
    vv_in_range = sum(1 for m in vv_means if vv_lo <= m <= vv_hi)
    vh_in_range = sum(1 for m in vh_means if vh_lo <= m <= vh_hi)
    print(f"VV scene-means within v0.2 clip range [{vv_lo},{vv_hi}]: {vv_in_range}/{len(vv_means)}")
    print(f"VH scene-means within v0.2 clip range [{vh_lo},{vh_hi}]: {vh_in_range}/{len(vh_means)}")

    summary = {
        "n_scenes": len(per_scene),
        "vv_brighter_fraction": n_ok / len(per_scene) if per_scene else None,
        "vv_mean_of_means_db": float(np.mean(vv_means)) if vv_means else None,
        "vh_mean_of_means_db": float(np.mean(vh_means)) if vh_means else None,
        "vv_in_v02_range_count": vv_in_range,
        "vh_in_v02_range_count": vh_in_range,
        "v02_clip_reference": V02_CLIP,
    }
    with open(PROV_DIR / "phase5_8_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
