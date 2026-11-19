"""
NETRA Experiment A -- MC20 NESZ implementation audit + corrected comparison.

Read-only w.r.t. raw SAFE, MC20 Event Gold, frozen checkpoint,
NETRA-GOLD-v0.2, official test split. Writes ONLY under
reports/netra_v02/experimentA_nesz/.

Three-way comparison:
  A. ORIGINAL   -- production calibrate_window() (no noise removal)
  B. EXP-0      -- NESZ removal, below_noise_policy="floor"  (arbitrary -115 dB constant)
  C. EXP-A      -- NESZ removal, below_noise_policy="mask"   (below-noise = unmeasurable/NaN)

The only difference between B and C is how physically-unmeasurable pixels
are represented. Neither changes the noise model itself, which this audit
verified is correctly implemented (see EXPERIMENT_A_NESZ_AUDIT.md).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import torch
import xml.etree.ElementTree as ET
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "packages"))
Image.MAX_IMAGE_PIXELS = None

from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    apply_netra_normalization, calibrate_to_db_denoised, parse_calibration_lut,
    parse_noise_lut, _interpolate_noise_to_grid, tile_512,
)
import varuna_data_eng.preprocessing.sentinel1_grd_calibration as calmod  # noqa: E402
import segmentation_models_pytorch as smp  # noqa: E402
from varuna_netra.training.evaluator import OIL_CLASS  # noqa: E402

OUT_DIR = REPO / "reports" / "netra_v02" / "experimentA_nesz"
WINDOW, MC20_LAT, MC20_LON = 1536, 28.936, -88.970
SAFE_DIR = (REPO / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15" /
            "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE")
CKPT = REPO / "artifacts" / "checkpoints" / "netra_v0_2" / "netra_baseline_v02_dac482fcd84a_best.pt"
GOLD_MANIFEST = REPO / "data" / "manifests" / "netra_gold_v0_2.json"
ANN, CAL, MEAS = SAFE_DIR / "annotation", SAFE_DIR / "annotation" / "calibration", SAFE_DIR / "measurement"
VV_ANN = ANN / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VV_CAL = CAL / "calibration-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VH_CAL = CAL / "calibration-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
VV_NOISE = CAL / "noise-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VH_NOISE = CAL / "noise-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
VV_TIFF = MEAS / "s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.tiff"
VH_TIFF = MEAS / "s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.tiff"

ZENODO_REF = {"VV": {"mean": -34.78, "std": 4.45}, "VH": {"mean": -20.14, "std": 2.68}}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    except Exception:
        return "unknown"


def find_crop() -> tuple[int, int]:
    pts = ET.parse(VV_ANN).getroot().findall(".//geolocationGridPoint")
    best, bd = None, None
    for p in pts:
        lat, lon = float(p.find("latitude").text), float(p.find("longitude").text)
        d = (lat - MC20_LAT) ** 2 + (lon - MC20_LON) ** 2
        if bd is None or d < bd:
            bd, best = d, (int(p.find("line").text), int(p.find("pixel").text))
    line, pixel = best
    W, H = Image.open(VV_TIFF).size
    half = WINDOW // 2
    return max(0, min(line - half, H - WINDOW)), max(0, min(pixel - half, W - WINDOW))


def read_dn(path: Path, top: int, left: int) -> np.ndarray:
    im = Image.open(path)
    t = im.tile[:2]
    base, stride, Wi = t[0].offset, t[1].offset - t[0].offset, im.size[0]
    assert stride == Wi * 2
    out = np.empty((WINDOW, WINDOW), dtype=np.uint16)
    with open(path, "rb") as f:
        for i, row in enumerate(range(top, top + WINDOW)):
            f.seek(base + row * stride + left * 2)
            out[i] = np.frombuffer(f.read(WINDOW * 2), dtype="<u2")
    return out


def calibrate_original(dn: np.ndarray, cal_xml: Path, top: int, left: int) -> np.ndarray:
    lut = parse_calibration_lut(cal_xml)
    sh = replace(lut, lines=lut.lines - top, pixels=lut.pixels - left)
    sg = calmod._interpolate_lut_to_grid(sh, dn.shape[0], dn.shape[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10((dn.astype(np.float64) ** 2) / (sg ** 2))
    return np.where(dn == 0, np.nan, db).astype(np.float32)


def stats(db: np.ndarray) -> dict:
    f = db[np.isfinite(db)]
    if f.size == 0:
        return {"n_valid": 0}
    gy, gx = np.gradient(np.nan_to_num(db, nan=float(np.median(f))).astype(np.float64))
    return {
        "n_valid": int(f.size), "valid_fraction": float(np.isfinite(db).mean()),
        "mean": float(f.mean()), "std": float(f.std()),
        "P1": float(np.percentile(f, 1)), "P5": float(np.percentile(f, 5)),
        "P25": float(np.percentile(f, 25)), "P50": float(np.percentile(f, 50)),
        "P75": float(np.percentile(f, 75)), "P95": float(np.percentile(f, 95)),
        "P99": float(np.percentile(f, 99)),
        "min": float(f.min()), "max": float(f.max()),
        "grad_mag_mean": float(np.sqrt(gx ** 2 + gy ** 2).mean()),
    }


def var_ratio(s: dict, ch: str) -> float:
    return (s["std"] / ZENODO_REF[ch]["std"]) ** 2


def probe(model, device, tiles, thr=0.806) -> dict:
    x = torch.from_numpy(np.stack(tiles)).float().to(device)
    with torch.no_grad(), torch.autocast("cuda", enabled=device.type == "cuda"):
        lg = model(x).float()
    p = torch.softmax(lg, 1)[:, OIL_CLASS].cpu().numpy()
    oil_logit = lg[:, OIL_CLASS].cpu().numpy()
    return {
        "max": float(p.max()), "mean": float(p.mean()),
        "P50": float(np.percentile(p, 50)), "P90": float(np.percentile(p, 90)),
        "P95": float(np.percentile(p, 95)), "P99": float(np.percentile(p, 99)),
        "foreground_fraction_at_0.806": float((p >= thr).mean()),
        "oil_logit_mean": float(oil_logit.mean()), "oil_logit_max": float(oil_logit.max()),
    }


def spatial_summary(arr: np.ndarray, name: str) -> dict:
    """Coarse block summary to judge spatial coherence vs localized pathology."""
    a = arr.astype(np.float64)
    B = 4  # 4x4 block grid over the 1536x1536 crop
    s = WINDOW // B
    blocks = [[float(np.nanmean(a[r * s:(r + 1) * s, c * s:(c + 1) * s])) for c in range(B)] for r in range(B)]
    finite = a[np.isfinite(a)]
    # range direction == columns, azimuth == rows
    col_prof = np.nanmean(a, axis=0)
    row_prof = np.nanmean(a, axis=1)
    return {
        "name": name, "block_means_4x4": blocks,
        "range_direction_col_profile_first_last": [float(col_prof[0]), float(col_prof[-1])],
        "azimuth_direction_row_profile_first_last": [float(row_prof[0]), float(row_prof[-1])],
        "range_profile_monotonic_trend": float(np.polyfit(np.arange(len(col_prof)), np.nan_to_num(col_prof, nan=float(np.nanmean(finite))), 1)[0]),
        "overall_mean": float(np.nanmean(a)),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    norm = json.loads(GOLD_MANIFEST.read_text(encoding="utf-8"))["normalization"]
    vvs, vhs = norm["channels"]["VV"], norm["channels"]["VH"]
    top, left = find_crop()
    print(f"[CROP] top={top} left={left}")

    vv_dn, vh_dn = read_dn(VV_TIFF, top, left), read_dn(VH_TIFF, top, left)

    # --- A. ORIGINAL ---
    vv_A, vh_A = calibrate_original(vv_dn, VV_CAL, top, left), calibrate_original(vh_dn, VH_CAL, top, left)

    # --- Phase 9: fidelity, original must still equal production Gold exactly ---
    tiles_A = [t.array for t in tile_512(apply_netra_normalization(vv_A, vh_A, vvs, vhs), "A")]
    real = [np.load(f) for f in sorted((REPO / "data/gold/events/mc20_v0_1/sar/tiles").glob("*.npy"))]
    fid = max(float(np.abs(a - b).max()) for a, b in
              zip(sorted(tiles_A, key=lambda t: t.sum()), sorted(real, key=lambda t: t.sum())))
    print(f"[FIDELITY] max_abs_diff vs production MC20 Gold = {fid}")
    if fid != 0.0:
        print("FIDELITY BROKEN -- stopping per Phase 9 stop condition.")
        (OUT_DIR / "FIDELITY_FAILURE.json").write_text(json.dumps({"max_abs_diff": fid}, indent=2))
        return 2

    # --- B. EXP-0 (floor) and C. EXP-A (mask) ---
    (vvB, n_bn_vv), (vhB, n_bn_vh) = (
        calibrate_to_db_denoised(vv_dn, VV_CAL, VV_NOISE, "VV", VV_TIFF, top, left, below_noise_policy="floor"),
        calibrate_to_db_denoised(vh_dn, VH_CAL, VH_NOISE, "VH", VH_TIFF, top, left, below_noise_policy="floor"))
    (vvC, _), (vhC, _) = (
        calibrate_to_db_denoised(vv_dn, VV_CAL, VV_NOISE, "VV", VV_TIFF, top, left, below_noise_policy="mask"),
        calibrate_to_db_denoised(vh_dn, VH_CAL, VH_NOISE, "VH", VH_TIFF, top, left, below_noise_policy="mask"))
    vv_B, vh_B, vv_C, vh_C = vvB.db, vhB.db, vvC.db, vhC.db

    total_px = WINDOW * WINDOW
    noise_floor = {
        "VV_below_noise_pixels": n_bn_vv, "VV_below_noise_fraction": n_bn_vv / total_px,
        "VH_below_noise_pixels": n_bn_vh, "VH_below_noise_fraction": n_bn_vh / total_px,
        "note": "Fraction of pixels whose signal power does not exceed the real, product-supplied "
                "thermal-noise floor. For these pixels sigma0 is physically UNMEASURABLE.",
    }
    print(f"[NOISE FLOOR] VV below-noise={n_bn_vv/total_px:.4f}  VH below-noise={n_bn_vh/total_px:.4f}")

    # SNR context
    g_vv = _interpolate_noise_to_grid(parse_noise_lut(VV_NOISE), WINDOW, WINDOW, top, left)
    g_vh = _interpolate_noise_to_grid(parse_noise_lut(VH_NOISE), WINDOW, WINDOW, top, left)
    snr = {
        "VV": {"dn2_mean": float((vv_dn.astype(float) ** 2).mean()), "noise_mean": float(g_vv.mean()),
                "snr_mean": float(((vv_dn.astype(float) ** 2) / g_vv).mean()),
                "snr_median": float(np.median((vv_dn.astype(float) ** 2) / g_vv))},
        "VH": {"dn2_mean": float((vh_dn.astype(float) ** 2).mean()), "noise_mean": float(g_vh.mean()),
                "snr_mean": float(((vh_dn.astype(float) ** 2) / g_vh).mean()),
                "snr_median": float(np.median((vh_dn.astype(float) ** 2) / g_vh))},
    }

    three_way = {}
    for label, vv, vh in [("A_original", vv_A, vh_A), ("B_exp0_floor", vv_B, vh_B), ("C_expA_mask", vv_C, vh_C)]:
        sv, sh = stats(vv), stats(vh)
        three_way[label] = {
            "VV": {**sv, "variance_ratio_vs_zenodo": var_ratio(sv, "VV")},
            "VH": {**sh, "variance_ratio_vs_zenodo": var_ratio(sh, "VH")},
        }
        print(f"[{label}] VV std={sv['std']:.3f} vr={var_ratio(sv,'VV'):.4f} | "
              f"VH std={sh['std']:.3f} vr={var_ratio(sh,'VH'):.4f} validVH={sh['valid_fraction']:.4f}")

    spatial = {
        "vh_noise_power": spatial_summary(g_vh, "VH_noise_power"),
        "vh_original_db": spatial_summary(vh_A, "VH_original_db"),
        "vh_corrected_masked_db": spatial_summary(vh_C, "VH_corrected_masked_db"),
        "vh_below_noise_mask": spatial_summary(
            ((vh_dn.astype(np.float64) ** 2) <= g_vh).astype(np.float64), "VH_below_noise_mask_fraction"),
        "vv_below_noise_mask": spatial_summary(
            ((vv_dn.astype(np.float64) ** 2) <= g_vv).astype(np.float64), "VV_below_noise_mask_fraction"),
    }

    # --- Phase 12: frozen model probe on all three ---
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    model = smp.Unet(encoder_name=ck.get("config", {}).get("encoder_name", "resnet34"),
                      encoder_weights=None, in_channels=2, classes=2)
    model.load_state_dict(ck["model_state_dict"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()

    probes = {}
    for label, vv, vh in [("A_original", vv_A, vh_A), ("B_exp0_floor", vv_B, vh_B), ("C_expA_mask", vv_C, vh_C)]:
        tiles = [t.array for t in tile_512(apply_netra_normalization(vv, vh, vvs, vhs), label)]
        probes[label] = probe(model, device, tiles)
        print(f"[PROBE {label}] max={probes[label]['max']:.6e} fg@0.806={probes[label]['foreground_fraction_at_0.806']}")

    result = {
        "experiment_id": "experimentA_nesz_audit", "date": "2026-08-30",
        "git_commit": git_commit(),
        "ipf_version": "003.52",
        "crop_window": {"top": top, "left": left, "size": WINDOW},
        "calibration_fidelity_check": {"max_abs_diff_vs_production_gold": fid, "status": "PASS (exact)"},
        "signal_to_noise": snr,
        "noise_floor_analysis": noise_floor,
        "three_way_comparison": three_way,
        "spatial_analysis": spatial,
        "frozen_netra_probe": probes,
        "checkpoint_sha256": hashlib.sha256(CKPT.read_bytes()).hexdigest(),
    }
    (OUT_DIR / "experimentA_nesz_audit_raw.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote -> {OUT_DIR / 'experimentA_nesz_audit_raw.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
