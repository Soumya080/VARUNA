"""B1 PR-curve / score-distribution diagnostic (2026-09-01).

READ-ONLY. Forward-pass inference only (no backward, no optimizer, no
training). Refuses to run on anything but the CALM-GRD-HOLDOUT split.
Does not select or write a deployment threshold; the frozen v0.806
threshold is reported alongside the observational sweep, never replaced.

No stored per-pixel score arrays existed on disk before this script
(08_b1_final_evaluation.py only persisted derived scalars from its
in-memory histogram) -- this is the minimal necessary rerun to answer
the diagnostic question, not a re-evaluation of the experiment.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "packages"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from varuna_netra.model.config import NetraModelConfig
from varuna_netra.model.factory import create_netra_model
from varuna_netra.dataset.gold_v03 import NetraGoldV03Dataset, IGNORE_INDEX

B1_CHECKPOINT = REPO / "artifacts" / "experiments" / "netra_v03" / "pilot_01_run2" / "last.pt"
V02_CHECKPOINT = REPO / "artifacts" / "checkpoints" / "netra_v0_2" / "netra_baseline_v02_dac482fcd84a_best.pt"
EXPECTED_B1_SHA = "3b76c589ac220687c78e5db38be171294657ec6819413fd9af32221f6f8e12dd"
EXPECTED_V02_SHA = "9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66"

TILE_RECORDS = REPO / "data" / "gold" / "netra_v0_3" / "provenance" / "tile_records_v2.json"
NORM_FILE = REPO / "data" / "gold" / "netra_v0_3" / "reports" / "normalization_v02_compat.json"
OUT_DIR = REPO / "artifacts" / "experiments" / "netra_v03" / "pilot_01_run2" / "score_diagnostic"
REPORT_JSON = REPO / "reports" / "netra_v03" / "b1_score_diagnostic.json"

THRESHOLD = 0.806
OIL_CLASS = 1
PR_BINS = 1024
SWEEP_THRESHOLDS = np.linspace(0.0, 1.0, 41)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_model(ckpt_path: Path, device):
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    model = create_netra_model(NetraModelConfig(
        encoder_name="resnet34", encoder_weights=None, in_channels=2, classes=2,
    )).to(device)
    state = ck["model"] if "model" in ck else ck.get("model_state_dict", ck)
    model.load_state_dict(state)
    model.eval()
    return model


def hist_percentiles(hist: np.ndarray, bins: np.ndarray, qs=(50, 90, 95, 99)):
    total = hist.sum()
    if total == 0:
        return {f"p{q}": None for q in qs}
    cdf = np.cumsum(hist) / total
    out = {}
    for q in qs:
        idx = int(np.searchsorted(cdf, q / 100.0))
        idx = min(idx, len(bins) - 1)
        out[f"p{q}"] = float(bins[idx])
    return out


def pr_curve_from_hist(pos_hist, neg_hist):
    """Full PR curve (not just AUC) at PR_BINS thresholds, high->low score,
    plus the histogram-derived AUC as an integrity cross-check against the
    scalar already recorded in the final evaluation report."""
    pos_cum = np.cumsum(pos_hist[::-1])[::-1]  # pixels with score >= bin i
    neg_cum = np.cumsum(neg_hist[::-1])[::-1]
    tp = pos_cum.astype(np.float64)
    fp = neg_cum.astype(np.float64)
    fn = pos_hist.sum() - tp
    precision = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), 1.0)
    recall = np.where(pos_hist.sum() > 0, tp / max(pos_hist.sum(), 1), 0.0)
    order = np.argsort(recall)
    r_sorted, p_sorted = recall[order], precision[order]
    auc = float(np.trapezoid(p_sorted, r_sorted))
    f1 = np.where(precision + recall > 0, 2 * precision * recall / np.maximum(precision + recall, 1e-12), 0.0)
    best_idx = int(np.argmax(f1))
    return {
        "pr_auc_from_histogram": auc,
        "best_f1": float(f1[best_idx]),
        "best_f1_threshold": float(best_idx / (PR_BINS - 1)),
        "recall_curve": recall[::32].tolist(),   # downsampled for JSON size
        "precision_curve": precision[::32].tolist(),
        "thresholds_curve": (np.arange(PR_BINS) / (PR_BINS - 1))[::32].tolist(),
    }


@torch.no_grad()
def run_model(model, dataset, device, spatial_sample_ids):
    bins = np.arange(PR_BINS) / (PR_BINS - 1)
    pos_hist = np.zeros(PR_BINS, dtype=np.int64)
    neg_hist = np.zeros(PR_BINS, dtype=np.int64)
    box_interior_hist = np.zeros(PR_BINS, dtype=np.int64)  # ignore-region scores, informational only

    fg_frac_at_thr = {float(t): [0, 0] for t in SWEEP_THRESHOLDS}  # [count_fg_px, count_total_px]
    spatial = {}

    loader = torch.utils.data.DataLoader(dataset, batch_size=4, shuffle=False, num_workers=0)
    t0 = time.perf_counter()
    idx_global = 0
    for images, targets, meta in loader:
        images = images.to(device)
        targets = targets.to(device)
        logits = model(images).float()
        probs = torch.softmax(logits, dim=1)[:, OIL_CLASS]

        valid = targets != IGNORE_INDEX
        ignore_mask = targets == IGNORE_INDEX
        tgt_pos = (targets == OIL_CLASS) & valid

        vp = probs[valid]
        vt = tgt_pos[valid]
        binned = np.clip((vp.cpu().numpy() * (PR_BINS - 1)).astype(np.int64), 0, PR_BINS - 1)
        vt_np = vt.cpu().numpy()
        pos_hist += np.bincount(binned[vt_np], minlength=PR_BINS)
        neg_hist += np.bincount(binned[~vt_np], minlength=PR_BINS)

        if ignore_mask.any():
            ig = probs[ignore_mask].cpu().numpy()
            ib = np.clip((ig * (PR_BINS - 1)).astype(np.int64), 0, PR_BINS - 1)
            box_interior_hist += np.bincount(ib, minlength=PR_BINS)

        for t in SWEEP_THRESHOLDS:
            fg = ((probs >= t) & valid).sum().item()
            fg_frac_at_thr[float(t)][0] += fg
            fg_frac_at_thr[float(t)][1] += int(valid.sum().item())

        b = images.shape[0]
        for i in range(b):
            sid = meta["sample_id"][i]
            if sid in spatial_sample_ids:
                p_i = probs[i].cpu().numpy()
                v_i = valid[i].cpu().numpy()
                pos_i = tgt_pos[i].cpu().numpy()
                ig_i = ignore_mask[i].cpu().numpy()
                pred_fg = (p_i >= THRESHOLD) & v_i
                n_cc = None
                try:
                    from scipy import ndimage
                    lbl, n_cc = ndimage.label(pred_fg)
                except Exception:
                    pass
                spatial[sid] = {
                    "true_oil_region_mean_score": float(p_i[pos_i].mean()) if pos_i.any() else None,
                    "background_mean_score": float(p_i[v_i & ~pos_i].mean()) if (v_i & ~pos_i).any() else None,
                    "box_interior_mean_score": float(p_i[ig_i].mean()) if ig_i.any() else None,
                    "predicted_foreground_fraction": float(pred_fg.mean()),
                    "n_connected_components": int(n_cc) if n_cc is not None else None,
                    "max_score_in_tile": float(p_i.max()),
                }
        idx_global += b

    elapsed = time.perf_counter() - t0
    pos_pct = hist_percentiles(pos_hist, bins)
    neg_pct = hist_percentiles(neg_hist, bins)
    box_pct = hist_percentiles(box_interior_hist, bins)
    pr = pr_curve_from_hist(pos_hist, neg_hist)

    fg_sweep = {str(t): (v[0] / v[1] if v[1] else None) for t, v in fg_frac_at_thr.items()}

    return {
        "eval_seconds": round(elapsed, 2),
        "n_tiles": idx_global,
        "positive_region_score": {"n_px": int(pos_hist.sum()), **pos_pct},
        "negative_region_score": {"n_px": int(neg_hist.sum()), **neg_pct},
        "box_interior_ignore_score": {"n_px": int(box_interior_hist.sum()), **box_pct},
        "pr_curve": pr,
        "foreground_fraction_by_threshold": fg_sweep,
        "spatial_examples": spatial,
    }, {"pos_hist": pos_hist, "neg_hist": neg_hist, "box_hist": box_interior_hist}


def main():
    if sha256_file(B1_CHECKPOINT) != EXPECTED_B1_SHA:
        raise SystemExit("REFUSING: B1 checkpoint hash mismatch")
    if sha256_file(V02_CHECKPOINT) != EXPECTED_V02_SHA:
        raise SystemExit("REFUSING: v0.2 checkpoint hash mismatch")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    norm = json.loads(NORM_FILE.read_text())

    # apply_ignore=False, matching 08_b1_final_evaluation.py exactly: for
    # SCORING (not training) the box interior is read as target=1 -- the
    # only available ground-truth proxy, distinct from the ignore-based
    # training-time semantics used in the MIL loss itself.
    ds = NetraGoldV03Dataset(TILE_RECORDS, split="holdout", repo_root=REPO,
                             normalization=norm, apply_ignore=False, return_meta=True)
    print(f"holdout tiles: {len(ds)}  (must equal 215 per the final evaluation report)")

    # deterministic spatial sample: first 10 oil-class tiles, sorted tile_id (already the loader's own order)
    spatial_ids = set()
    for r in ds.records:
        if r["semantic_class"] == "OIL":
            spatial_ids.add(r["sample_id"])
        if len(spatial_ids) >= 10:
            break

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, ckpt in [("v0_2", V02_CHECKPOINT), ("b1", B1_CHECKPOINT)]:
        print(f"\n=== running {name} ===")
        model = load_model(ckpt, device)
        res, hists = run_model(model, ds, device, spatial_ids)
        results[name] = res
        np.savez(OUT_DIR / f"{name}_score_histograms.npz", **hists)
        print(f"  eval_seconds={res['eval_seconds']}  pos_p50={res['positive_region_score']['p50']}  "
              f"neg_p50={res['negative_region_score']['p50']}  pr_auc_hist={res['pr_curve']['pr_auc_from_histogram']:.4f}")
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()

    report = {
        "diagnostic_id": "b1_score_diagnostic",
        "date": "2026-09-01",
        "question": "Did B1 lose ranking ability, or shift/suppress its score distribution?",
        "checkpoints_verified": {"v0_2_sha256": EXPECTED_V02_SHA, "b1_sha256": EXPECTED_B1_SHA},
        "holdout_tiles": len(ds),
        "frozen_threshold": THRESHOLD,
        "results": results,
        "raw_histograms_saved_to": str(OUT_DIR.relative_to(REPO)),
        "diagnostic_only": "This threshold sweep is observational. No threshold was selected, "
                            "no model was modified, no deployment decision is made here.",
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, default=lambda x: None))
    print(f"\nwritten: {REPORT_JSON}")


if __name__ == "__main__":
    main()
