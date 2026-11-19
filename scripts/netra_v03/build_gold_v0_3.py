"""Build data/gold/netra_v0_3/ from the 25 acquired+verified ESSD/PANGAEA
GRD scenes. Does NOT touch data/gold/netra_v0_2/, Zenodo Part III, or
MC20. Tile size 512x512, matching v0.2's own convention.

Split logic (scene-level, decided BEFORE tiling, same order as v0.2):
  - HOLDOUT (CALM-GRD-HOLDOUT): the 14 scenes that are BOTH low-wind
    (real ERA5) AND geographically clean (>=15km from any sampled
    Zenodo Part I/II/III tile centroid) -- see
    provenance/calm_grd_holdout_candidates.json.
  - TRAIN: the remaining 11 scenes.
  - No VAL split yet -- 11 train scenes is too few to further subdivide
    into a meaningful val split without emptying train; documented as a
    known limitation, not silently worked around.

Label quality (recorded explicitly, not glossed over): PANGAEA supplies
PASCAL-VOC bounding boxes, not pixel-precise segmentation masks like
Zenodo. Masks here are the object bbox rasterized as a filled
rectangle -- a coarse approximation, flagged in every tile's
quality_flags.

Tiling strategy (label-centered, not exhaustive-grid): for TRAIN, a
512x512 window centered on each real reprojected object (oil) or patch
region (negative), clipped to scene bounds -- this is a first-experiment
scale dataset, not an attempt to exhaustively cover each multi-GB scene.
"""
from __future__ import annotations

import glob
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import rasterio
from scipy.interpolate import griddata

REPO = Path(__file__).resolve().parents[2]
EXTRACTED = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "extracted"
PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"
GOLD_DIR = REPO / "data" / "gold" / "netra_v0_3"
TILE_SIZE = 512


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "UNKNOWN"


def parse_calib_lut(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    vectors = root.findall(".//calibrationVector")
    lines, pixels_list, sigma_list = [], [], []
    for vec in vectors:
        lines.append(int(vec.find("line").text))
        pixels_list.append(np.array([int(p) for p in vec.find("pixel").text.split()]))
        sigma_list.append(np.array([float(s) for s in vec.find("sigmaNought").text.split()]))
    return np.array(lines), np.stack(pixels_list), np.stack(sigma_list)


def sigma_at_window(lines, pixels, sigma, line0, pixel0, h, w):
    from scipy.interpolate import RegularGridInterpolator
    interp = RegularGridInterpolator((lines, pixels[0]), sigma, bounds_error=False, fill_value=None)
    line_grid, pixel_grid = np.meshgrid(
        np.arange(line0, line0 + h), np.arange(pixel0, pixel0 + w), indexing="ij"
    )
    pts = np.stack([line_grid.ravel(), pixel_grid.ravel()], axis=-1)
    return interp(pts).reshape(h, w)


def calibrate_window(tiff_path, calib_xml, line0, pixel0, h, w):
    with rasterio.open(tiff_path) as src:
        window = rasterio.windows.Window(pixel0, line0, w, h)
        dn = src.read(1, window=window).astype(np.float64)
    lines, pixels, sigma = parse_calib_lut(calib_xml)
    sigma_grid = sigma_at_window(lines, pixels, sigma, line0, pixel0, dn.shape[0], dn.shape[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma0_linear = (dn ** 2) / (sigma_grid ** 2)
        db = 10.0 * np.log10(sigma0_linear)
    db = np.where(dn == 0, np.nan, db)
    return db.astype(np.float32)


def scene_paths(scene_dir: Path):
    vv_tiff = next(iter(glob.glob(str(scene_dir / "measurement" / "*-vv-*.tiff"))))
    vh_tiff = next(iter(glob.glob(str(scene_dir / "measurement" / "*-vh-*.tiff"))))
    vv_cal = next(iter(glob.glob(str(scene_dir / "annotation" / "calibration" / "calibration-*-vv-*.xml"))))
    vh_cal = next(iter(glob.glob(str(scene_dir / "annotation" / "calibration" / "calibration-*-vh-*.xml"))))
    return vv_tiff, vh_tiff, vv_cal, vh_cal


def main():
    with open(PROV_DIR / "calm_grd_holdout_candidates.json") as f:
        holdout_cand = json.load(f)
    holdout_scenes = set(holdout_cand["oil"] + holdout_cand["negative"])

    with open(PROV_DIR / "reprojected_labels.json") as f:
        labels = json.load(f)
    with open(PROV_DIR / "era5_regime_join.json") as f:
        regime = json.load(f)
    regime_by_scene = {r["sentinel_product_id"]: r for r in regime}

    scene_names = sorted({l["sentinel_product_id"] for l in labels})
    train_scenes = [s for s in scene_names if s not in holdout_scenes]
    print(f"holdout scenes: {len(holdout_scenes)}, train scenes: {len(train_scenes)}")

    for sub in ["train", "holdout"]:
        (GOLD_DIR / sub).mkdir(parents=True, exist_ok=True)
    (GOLD_DIR / "reports").mkdir(parents=True, exist_ok=True)
    (GOLD_DIR / "provenance").mkdir(parents=True, exist_ok=True)

    from collections import defaultdict
    labels_by_scene = defaultdict(list)
    for l in labels:
        labels_by_scene[l["sentinel_product_id"]].append(l)

    tile_records = []
    half = TILE_SIZE // 2

    for scene_name in scene_names:
        split = "holdout" if scene_name in holdout_scenes else "train"
        scene_dir = EXTRACTED / scene_name
        try:
            vv_tiff, vh_tiff, vv_cal, vh_cal = scene_paths(scene_dir)
        except StopIteration:
            print(f"[skip] {scene_name}: missing measurement/calibration")
            continue
        with rasterio.open(vv_tiff) as s:
            H, W = s.height, s.width

        scene_regime = regime_by_scene.get(scene_name, {})

        n_tiles_this_scene = 0
        for rec in labels_by_scene[scene_name]:
            lmin, lmax = rec["raw_bbox_line_min_max"]
            pmin, pmax = rec["raw_bbox_pixel_min_max"]
            cy = int((lmin + lmax) / 2)
            cx = int((pmin + pmax) / 2)
            line0 = max(0, min(H - TILE_SIZE, cy - half))
            pixel0 = max(0, min(W - TILE_SIZE, cx - half))
            if H < TILE_SIZE or W < TILE_SIZE:
                continue

            vv_db = calibrate_window(vv_tiff, vv_cal, line0, pixel0, TILE_SIZE, TILE_SIZE)
            vh_db = calibrate_window(vh_tiff, vh_cal, line0, pixel0, TILE_SIZE, TILE_SIZE)
            # canonical v0.3 channel order (see NETRA_V03_POLARIZATION_CONTRACT.md):
            # channel 0 = VH, channel 1 = VV. This source's files are
            # unambiguously VV/VH by filename+brightness check -- no swap needed.
            img = np.stack([vh_db, vv_db], axis=0)  # (2, H, W)

            mask = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
            if rec["label"] == "oil":
                y0, y1 = max(0, lmin - line0), min(TILE_SIZE, lmax - line0)
                x0, x1 = max(0, pmin - pixel0), min(TILE_SIZE, pmax - pixel0)
                if y1 > y0 and x1 > x0:
                    mask[int(y0):int(y1), int(x0):int(x1)] = 1

            tile_id = f"{scene_name}__{rec['tag']}"
            img_path = GOLD_DIR / split / f"{tile_id}_img.npy"
            mask_path = GOLD_DIR / split / f"{tile_id}_mask.npy"
            np.save(img_path, img.astype(np.float32))
            np.save(mask_path, mask)

            tile_records.append({
                "tile_id": tile_id,
                "scene_id": scene_name,
                "source_dataset": "essd_grd_v03",
                "split": split,
                "label": rec["label"],
                "class": 1 if rec["label"] == "oil" else 0,
                "line0": line0, "pixel0": pixel0, "tile_size": TILE_SIZE,
                "physical_polarization_mapping": "channel0=VH,channel1=VV",
                "acquisition_timestamp": scene_regime.get("scene_start_time", "UNKNOWN"),
                "latitude": rec["corners_lonlat_and_raw_pixel"][0]["lat"],
                "longitude": rec["corners_lonlat_and_raw_pixel"][0]["lon"],
                "wind_speed_ms": scene_regime.get("wind_speed_ms"),
                "wind_regime": scene_regime.get("wind_regime", "unknown"),
                "environmental_source": "ERA5 (real, CDS API)" if scene_regime.get("wind_speed_ms") is not None else "UNKNOWN",
                "label_provenance": "PANGAEA.980773 bounding box, reprojected via geolocationGridPoint inverse interpolation",
                "label_type": "bbox_derived_coarse_mask",
                "preprocessing_version": "essd_grd_v03_phase1",
                "noise_convention": "no thermal-noise subtraction (matches v0.2's calibrate_to_db, not the denoised path)",
                "quality_flags": ["coarse_bbox_mask_not_pixel_precise"] + (
                    ["proximity_to_zenodo_lt_15km"] if scene_name not in holdout_scenes and False else []
                ),
            })
            n_tiles_this_scene += 1

        print(f"{scene_name[:45]:45s} split={split:8s} tiles={n_tiles_this_scene}")

    manifest = {
        "dataset_id": "netra_essd_grd_v03",
        "dataset_version": "NETRA-GOLD-v0.3-candidate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "pipeline_stage_scripts": [
            "scripts/netra_v03/download_essd_grd_scenes.py",
            "scripts/netra_v03/fetch_era5_essd_grd.py",
            "scripts/netra_v03/era5_join_and_regime.py",
            "scripts/netra_v03/reproject_essd_labels.py",
            "scripts/netra_v03/verify_reprojection.py",
            "scripts/netra_v03/build_gold_v0_3.py",
        ],
        "scientific_status": "EXPERIMENTAL / UNVALIDATED / FIRST CANDIDATE",
        "source_datasets": [{
            "id": "essd_grd_v03",
            "role": "OIL_POSITIVE_AND_HARD_NEGATIVE",
            "pangaea_doi": "10.1594/PANGAEA.980773",
            "essd_paper_doi": "10.5194/essd-17-6807-2025",
            "license": "CC-BY-4.0",
            "n_scenes": len(scene_names),
        }],
        "channels": ["VH", "VV"],
        "label_mapping": {
            "classes": {"0": "NOT_OIL", "1": "OIL"},
            "policy": "PANGAEA bounding boxes rasterized as filled-rectangle masks -- coarse, not pixel-precise. Negative/lookalike rows carry all-zero masks; PANGAEA's no-oil set combines lookalikes and other benign phenomena without a further per-row split (see ESSD_GRD_ACQUISITION_REPORT.md Phase 9).",
        },
        "tiling": {"tile_size": TILE_SIZE, "strategy": "label-centered (one tile per real reprojected object/patch region), not exhaustive grid"},
        "counts": {
            "scenes_total": len(scene_names),
            "scenes_train": len(train_scenes),
            "scenes_holdout": len(holdout_scenes),
            "tiles_total": len(tile_records),
            "tiles_train": sum(1 for t in tile_records if t["split"] == "train"),
            "tiles_holdout": sum(1 for t in tile_records if t["split"] == "holdout"),
            "tiles_oil": sum(1 for t in tile_records if t["class"] == 1),
            "tiles_negative": sum(1 for t in tile_records if t["class"] == 0),
        },
        "split": {
            "method": "scene-level, decided before tiling",
            "holdout_definition": "CALM-GRD-HOLDOUT: low-wind (real ERA5, <5m/s) AND >=15km from any sampled Zenodo Part I/II/III tile centroid",
            "holdout_scenes": sorted(holdout_scenes),
            "train_scenes": sorted(train_scenes),
            "known_limitation": "no separate val split -- only 11 train scenes, too few to further subdivide without emptying train",
        },
        "leakage": {
            "vs_mc20": "geographically disjoint (measured, bbox comparison, zero overlap possible)",
            "vs_zenodo_part1_2_3": "proximity-checked (haversine centroid distance, 200-tile deterministic sample per source, not exhaustive over full corpora); 8/25 scenes flagged <15km and excluded from holdout candidacy; holdout built only from the 17 clean scenes' low-wind subset",
            "exhaustive": False,
            "report": "data/raw/netra_v03_sources/essd_grd/provenance/leakage_geographic_report.json, leakage_proximity_report.json, per_scene_proximity.json",
        },
        "provenance": {
            "acquisition_log": "data/raw/netra_v03_sources/essd_grd/provenance/scene_acquisition_log.json",
            "era5_source": "real CDS API pull, data/raw/netra_v03_sources/essd_grd/era5_eastern_med_2019.nc",
            "reprojection_verification": "data/raw/netra_v03_sources/essd_grd/provenance/reprojection_verification.json (all 3 tests pass)",
        },
        "normalization": "NOT_YET_COMPUTED",  # filled in by the next script
    }
    with open(GOLD_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    with open(GOLD_DIR / "provenance" / "tile_records.json", "w") as f:
        json.dump(tile_records, f, indent=2)

    print(f"\nTotal tiles: {len(tile_records)} (train={manifest['counts']['tiles_train']}, holdout={manifest['counts']['tiles_holdout']})")
    print(f"oil={manifest['counts']['tiles_oil']} negative={manifest['counts']['tiles_negative']}")


if __name__ == "__main__":
    main()
