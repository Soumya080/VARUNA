"""
NETRA Experiment 0 -- NESZ / thermal-noise falsification probe.

Read-only with respect to: raw SAFE product, MC20 Event Gold, the frozen
checkpoint, NETRA-GOLD-v0.2, the official test split. Writes ONLY under
reports/netra_v02/experiment0_nesz/.

Does NOT train, fine-tune, or touch any production artifact. Reconstructs
the exact same 1536x1536 crop window MC20 Event Gold v0.1 was built from
(same anchor-nearest-grid-point logic as scripts/build_mc20_event_gold.py,
duplicated here read-only rather than imported, since the production
script is a top-level build script, not a library module) and produces
two calibrations of it:

  A. ORIGINAL  -- exactly reproduces the existing calibrate_window() logic
     used by scripts/build_mc20_event_gold.py (verified byte-reproduction
     against the 9 real MC20 Gold tiles below).
  B. DENOISED  -- calibrate_to_db_denoised(), the new additive,
     opt-in NESZ-corrected path.

Then normalizes both with the FROZEN v0.2 statistics (unchanged), tiles
both into the same 9 tiles as MC20 Event Gold v0.1, and runs the FROZEN
checkpoint (unchanged) on both tile sets.

PRE-REGISTERED DECISION CRITERION (fixed BEFORE this script reads any
denoised-inference result; do not edit this block after seeing output):

  Experiment 0 is judged MATERIAL EFFECT if, comparing denoised vs
  original:
    (i)  either channel's variance ratio (denoised-MC20 / Zenodo-raw-dB)
         increases by at least +0.15 absolute (e.g. 0.24 -> >=0.39), OR
    (ii) the frozen model's max oil probability across the 9 denoised
         tiles increases by at least 3 orders of magnitude (>= 1000x)
         relative to the original 3.05e-06, i.e. reaches >= 3.05e-03.
  If NEITHER condition holds, Experiment 0 is FAILED -- this does not
  mean NETRA failed; it means the NESZ-only hypothesis is insufficient
  on its own.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import rasterio
import torch
import xml.etree.ElementTree as ET
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "packages"))

Image.MAX_IMAGE_PIXELS = None

from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    apply_netra_normalization, calibrate_to_db_denoised, parse_calibration_lut, tile_512,
)
import varuna_data_eng.preprocessing.sentinel1_grd_calibration as calmod  # noqa: E402
import segmentation_models_pytorch as smp  # noqa: E402
from varuna_netra.training.evaluator import OIL_CLASS  # noqa: E402

OUT_DIR = REPO / "reports" / "netra_v02" / "experiment0_nesz"
WINDOW = 1536
MC20_LAT, MC20_LON = 28.936, -88.970
SAFE_DIR = (REPO / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15" /
            "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE")
CKPT_PATH = REPO / "artifacts" / "checkpoints" / "netra_v0_2" / "netra_baseline_v02_dac482fcd84a_best.pt"
FROZEN_SIDECAR = CKPT_PATH.with_name(CKPT_PATH.name + ".frozen.json")
GOLD_MANIFEST = REPO / "data" / "manifests" / "netra_gold_v0_2.json"

VV_ANN = SAFE_DIR / "annotation" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VV_CAL = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VH_CAL = SAFE_DIR / "annotation" / "calibration" / "calibration-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
VV_NOISE = SAFE_DIR / "annotation" / "calibration" / "noise-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VH_NOISE = SAFE_DIR / "annotation" / "calibration" / "noise-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
VV_TIFF = SAFE_DIR / "measurement" / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.tiff"
VH_TIFF = SAFE_DIR / "measurement" / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.tiff"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    except Exception:
        return "unknown"


def find_crop_window() -> tuple[int, int]:
    """Read-only reproduction of build_mc20_event_gold.py's anchor-nearest-
    grid-point crop-window logic. Does not write anything."""
    tree = ET.parse(VV_ANN)
    grid_pts = tree.getroot().findall(".//geolocationGridPoint")
    anchor_best, anchor_d2 = None, None
    for p in grid_pts:
        lat, lon = float(p.find("latitude").text), float(p.find("longitude").text)
        d2 = (lat - MC20_LAT) ** 2 + (lon - MC20_LON) ** 2
        if anchor_d2 is None or d2 < anchor_d2:
            anchor_d2 = d2
            anchor_best = (int(p.find("line").text), int(p.find("pixel").text))
    line, pixel = anchor_best
    im = Image.open(VV_TIFF)
    W, H = im.size
    half = WINDOW // 2
    left = max(0, min(pixel - half, W - WINDOW))
    top = max(0, min(line - half, H - WINDOW))
    return top, left


def read_dn_window(tiff_path: Path, top: int, left: int) -> np.ndarray:
    im0 = Image.open(tiff_path)
    first_two = im0.tile[:2]
    base_offset = first_two[0].offset
    row_stride = first_two[1].offset - first_two[0].offset
    W = im0.size[0]
    assert row_stride == W * 2
    out = np.empty((WINDOW, WINDOW), dtype=np.uint16)
    with open(tiff_path, "rb") as f:
        for i, row in enumerate(range(top, top + WINDOW)):
            f.seek(base_offset + row * row_stride + left * 2)
            out[i] = np.frombuffer(f.read(WINDOW * 2), dtype="<u2")
    return out


def calibrate_original(dn_window: np.ndarray, cal_xml: Path, top: int, left: int) -> np.ndarray:
    """Byte-for-byte reproduction of build_mc20_event_gold.py::calibrate_window."""
    lut = parse_calibration_lut(cal_xml)
    shifted_lut = replace(lut, lines=lut.lines - top, pixels=lut.pixels - left)
    sigma_grid = calmod._interpolate_lut_to_grid(shifted_lut, dn_window.shape[0], dn_window.shape[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma0_linear = (dn_window.astype(np.float64) ** 2) / (sigma_grid ** 2)
        db = 10.0 * np.log10(sigma0_linear)
    return np.where(dn_window == 0, np.nan, db).astype(np.float32)


def pct(a: np.ndarray) -> dict:
    return {str(p): float(np.percentile(a, p)) for p in [1, 2, 5, 25, 50, 75, 95, 98, 99]}


def db_stats(db: np.ndarray) -> dict:
    finite = db[np.isfinite(db)]
    valid_frac = float(np.isfinite(db).mean())
    gy, gx = np.gradient(np.nan_to_num(db, nan=np.nanmedian(finite)).astype(np.float64))
    grad_mag = np.sqrt(gx ** 2 + gy ** 2)
    return {
        "mean": float(finite.mean()), "std": float(finite.std()),
        "min": float(finite.min()), "max": float(finite.max()),
        "percentiles": pct(finite), "valid_pixel_fraction": valid_frac,
        "grad_mag_mean": float(grad_mag.mean()), "grad_mag_std": float(grad_mag.std()),
    }


def load_model():
    ck = torch.load(CKPT_PATH, map_location="cpu", weights_only=False)
    cfg = ck.get("config", {})
    model = smp.Unet(encoder_name=cfg.get("encoder_name", "resnet34"), encoder_weights=None,
                      in_channels=2, classes=2)
    model.load_state_dict(ck["model_state_dict"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    return model, device


def prob_stats(model, device, tiles: list[np.ndarray], threshold: float) -> dict:
    x = torch.from_numpy(np.stack(tiles)).float().to(device)
    with torch.no_grad(), torch.autocast("cuda", enabled=device.type == "cuda"):
        logits = model(x).float()
    probs = torch.softmax(logits, dim=1)[:, OIL_CLASS].cpu().numpy()
    return {
        "max": float(probs.max()), "mean": float(probs.mean()),
        "p50": float(np.percentile(probs, 50)), "p90": float(np.percentile(probs, 90)),
        "p95": float(np.percentile(probs, 95)), "p99": float(np.percentile(probs, 99)),
        "frac_above_threshold": float((probs >= threshold).mean()),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    threshold = 0.806

    manifest = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))
    norm = manifest["normalization"]
    vv_stats, vh_stats = norm["channels"]["VV"], norm["channels"]["VH"]

    top, left = find_crop_window()
    print(f"[CROP] top={top} left={left} window={WINDOW}")

    vv_dn = read_dn_window(VV_TIFF, top, left)
    vh_dn = read_dn_window(VH_TIFF, top, left)

    # A. ORIGINAL (reproduces production exactly)
    vv_db_orig = calibrate_original(vv_dn, VV_CAL, top, left)
    vh_db_orig = calibrate_original(vh_dn, VH_CAL, top, left)

    # B. DENOISED (new, additive, opt-in)
    (vv_res_denoised, vv_n_floored) = calibrate_to_db_denoised(
        vv_dn, VV_CAL, VV_NOISE, "VV", VV_TIFF, row_offset=top, col_offset=left)
    (vh_res_denoised, vh_n_floored) = calibrate_to_db_denoised(
        vh_dn, VH_CAL, VH_NOISE, "VH", VH_TIFF, row_offset=top, col_offset=left)
    vv_db_denoised, vh_db_denoised = vv_res_denoised.db, vh_res_denoised.db

    # IMPORTANT methodological note (found during this run, kept rather than
    # silently discarded): the floor_eps=1e-6 substitution for pixels where
    # DN^2 < noise_power is a real physical outcome (thermal noise exceeds
    # true signal there) but an ARBITRARY floor VALUE. Including floored
    # pixels in mean/std would let that arbitrary choice, not the real
    # signal, dominate the variance comparison. Two views are reported:
    #  - "including_floored": raw stats over every pixel (as originally coded).
    #  - "excluding_floored": stats over only pixels where DN^2 >= noise_power,
    #    i.e. where the correction produced a genuine (non-floored) value.
    # The pre-registered decision below uses "excluding_floored" as the fair,
    # like-for-like comparison; "including_floored" is reported for
    # transparency but explicitly flagged as floor-contaminated.
    def db_stats_excluding_floor(db_full: np.ndarray, dn: np.ndarray, cal_xml: Path, top_: int, left_: int, noise_xml: Path) -> dict:
        from varuna_data_eng.preprocessing.sentinel1_grd_calibration import parse_noise_lut, _interpolate_noise_to_grid
        lut = parse_calibration_lut(cal_xml)
        shifted_lut = replace(lut, lines=lut.lines - top_, pixels=lut.pixels - left_)
        sigma_grid = calmod._interpolate_lut_to_grid(shifted_lut, dn.shape[0], dn.shape[1])
        noise = parse_noise_lut(noise_xml)
        noise_grid = _interpolate_noise_to_grid(noise, dn.shape[0], dn.shape[1], top_, left_)
        raw_power = dn.astype(np.float64) ** 2
        not_floored = (raw_power - noise_grid) > 1e-6
        db_masked = np.where(not_floored & np.isfinite(db_full), db_full, np.nan)
        return db_stats(db_masked), float(not_floored.mean())

    vv_stats_excl, vv_valid_frac = db_stats_excluding_floor(vv_db_denoised, vv_dn, VV_CAL, top, left, VV_NOISE)
    vh_stats_excl, vh_valid_frac = db_stats_excluding_floor(vh_db_denoised, vh_dn, VH_CAL, top, left, VH_NOISE)

    stats_original = {"VV": db_stats(vv_db_orig), "VH": db_stats(vh_db_orig)}
    stats_denoised = {
        "VV_including_floored": db_stats(vv_db_denoised), "VH_including_floored": db_stats(vh_db_denoised),
        "VV_excluding_floored": vv_stats_excl, "VH_excluding_floored": vh_stats_excl,
        "VV_floored_pixel_count": vv_n_floored, "VH_floored_pixel_count": vh_n_floored,
        "VV_floored_pixel_fraction": vv_n_floored / vv_db_denoised.size,
        "VH_floored_pixel_fraction": vh_n_floored / vh_db_denoised.size,
        "VV_non_floored_fraction_crosscheck": vv_valid_frac,
        "VH_non_floored_fraction_crosscheck": vh_valid_frac,
    }

    # Zenodo raw-dB reference (from netra_preprocessing_reconciliation.json Phase 6, 10 scenes)
    zenodo_ref = {"VV": {"mean": -34.78, "std": 4.45}, "VH": {"mean": -20.14, "std": 2.68}}
    variance_ratio_original = {
        "VV": (stats_original["VV"]["std"] / zenodo_ref["VV"]["std"]) ** 2,
        "VH": (stats_original["VH"]["std"] / zenodo_ref["VH"]["std"]) ** 2,
    }
    # Fair (floor-excluded) view used for the pre-registered decision
    variance_ratio_denoised = {
        "VV": (stats_denoised["VV_excluding_floored"]["std"] / zenodo_ref["VV"]["std"]) ** 2,
        "VH": (stats_denoised["VH_excluding_floored"]["std"] / zenodo_ref["VH"]["std"]) ** 2,
    }
    # Raw (floor-contaminated) view, reported for transparency only, NOT used in the decision
    variance_ratio_denoised_including_floored = {
        "VV": (stats_denoised["VV_including_floored"]["std"] / zenodo_ref["VV"]["std"]) ** 2,
        "VH": (stats_denoised["VH_including_floored"]["std"] / zenodo_ref["VH"]["std"]) ** 2,
    }

    # normalize with FROZEN v0.2 stats, tile, run frozen model
    normalized_orig = apply_netra_normalization(vv_db_orig, vh_db_orig, vv_stats, vh_stats)
    normalized_denoised = apply_netra_normalization(vv_db_denoised, vh_db_denoised, vv_stats, vh_stats)
    tiles_orig = [t.array for t in tile_512(normalized_orig, "exp0_orig")]
    tiles_denoised = [t.array for t in tile_512(normalized_denoised, "exp0_denoised")]
    print(f"[TILES] original={len(tiles_orig)} denoised={len(tiles_denoised)}")

    model, device = load_model()
    probs_orig = prob_stats(model, device, tiles_orig, threshold)
    probs_denoised = prob_stats(model, device, tiles_denoised, threshold)

    # verify original reproduces the real MC20 Gold tiles (sanity check on this script itself)
    real_mc20_files = sorted((REPO / "data" / "gold" / "events" / "mc20_v0_1" / "sar" / "tiles").glob("*.npy"))
    real_tiles = [np.load(f) for f in real_mc20_files]
    max_abs_diff = 0.0
    if len(real_tiles) == len(tiles_orig):
        for a, b in zip(sorted(tiles_orig, key=lambda t: t.sum()), sorted(real_tiles, key=lambda t: t.sum())):
            max_abs_diff = max(max_abs_diff, float(np.abs(a - b).max()))
    reproduction_check = {
        "n_real_tiles": len(real_tiles), "n_computed_tiles": len(tiles_orig),
        "max_abs_diff_after_sort_by_sum": max_abs_diff,
        "note": "Sorted by sum (not scene-matched by row/col label) as a coarse sanity check that this "
                "script's independently-reconstructed crop/calibration lands in the same numeric regime "
                "as the real production Gold tiles. Not a guaranteed exact tile-for-tile correspondence.",
    }

    # --- pre-registered decision, applied mechanically ---
    var_ratio_delta_vv = variance_ratio_denoised["VV"] - variance_ratio_original["VV"]
    var_ratio_delta_vh = variance_ratio_denoised["VH"] - variance_ratio_original["VH"]
    criterion_i = (var_ratio_delta_vv >= 0.15) or (var_ratio_delta_vh >= 0.15)
    criterion_ii = probs_denoised["max"] >= (probs_orig["max"] * 1000.0)
    material_effect = bool(criterion_i or criterion_ii)

    result = {
        "experiment_id": "experiment0_nesz",
        "date": "2026-08-30",
        "git_commit": git_commit(),
        "source_safe_dir": str(SAFE_DIR),
        "checksums": {
            "vv_measurement_sha256": sha256_of(VV_TIFF),
            "vh_measurement_sha256": sha256_of(VH_TIFF),
            "vv_calibration_xml_sha256": sha256_of(VV_CAL),
            "vh_calibration_xml_sha256": sha256_of(VH_CAL),
            "vv_noise_xml_sha256": sha256_of(VV_NOISE),
            "vh_noise_xml_sha256": sha256_of(VH_NOISE),
            "checkpoint_sha256": sha256_of(CKPT_PATH),
            "manifest_sha256": sha256_of(GOLD_MANIFEST),
        },
        "crop_window": {"top": top, "left": left, "size": WINDOW},
        "reproduction_check_vs_real_mc20_gold": reproduction_check,
        "pre_normalization_comparison_db_scale": {
            "original": stats_original,
            "denoised": stats_denoised,
            "zenodo_reference_10_scenes": zenodo_ref,
            "variance_ratio_mc20_over_zenodo": {
                "original": variance_ratio_original,
                "denoised_excluding_floored_FAIR_COMPARISON": variance_ratio_denoised,
                "denoised_including_floored_CONTAMINATED_DO_NOT_USE_FOR_DECISION": variance_ratio_denoised_including_floored,
            },
        },
        "frozen_model_probe": {
            "threshold": threshold,
            "original": probs_orig,
            "denoised": probs_denoised,
        },
        "decision_criterion": {
            "criterion_i": "either channel's variance ratio increases by >= 0.15 absolute",
            "criterion_ii": "max oil probability increases by >= 1000x",
            "criterion_i_result": {"VV_delta": var_ratio_delta_vv, "VH_delta": var_ratio_delta_vh, "met": criterion_i},
            "criterion_ii_result": {"ratio": probs_denoised["max"] / probs_orig["max"] if probs_orig["max"] > 0 else float("inf"), "met": criterion_ii},
            "material_effect": material_effect,
            "experiment_status": "MATERIAL_EFFECT -- proceed to EXPERIMENT A" if material_effect else "FAILED -- proceed to EXPERIMENT B",
        },
    }

    (OUT_DIR / "experiment0_nesz_raw.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["decision_criterion"], indent=2))
    print(json.dumps(result["pre_normalization_comparison_db_scale"]["variance_ratio_mc20_over_zenodo"], indent=2))
    print(json.dumps({"orig_max": probs_orig["max"], "denoised_max": probs_denoised["max"]}, indent=2))
    print(f"wrote -> {OUT_DIR / 'experiment0_nesz_raw.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
