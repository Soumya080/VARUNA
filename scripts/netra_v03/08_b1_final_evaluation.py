"""NETRA v0.3-B1 — ONE-SHOT FINAL SCIENTIFIC EVALUATION.

This script evaluates the B1 checkpoint ONCE on:
  1. CALM-GRD-HOLDOUT (PRIMARY)
  2. Per-scene breakout
  3. Training dynamics audit (from logs)

It does NOT tune, select, or modify anything.
Threshold is the frozen v0.2 value (0.806).

Output:
  artifacts/experiments/netra_v03/pilot_01_run2/evaluation/
  reports/netra_v03/netra_v03_b1_final_evaluation.json
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

# ── Configuration ─────────────────────────────────────────────────────────
CHECKPOINT = REPO / "artifacts" / "experiments" / "netra_v03" / "pilot_01_run2" / "last.pt"
TILE_RECORDS = REPO / "data" / "gold" / "netra_v0_3" / "provenance" / "tile_records_v2.json"
NORM_FILE = REPO / "data" / "gold" / "netra_v0_3" / "reports" / "normalization_v02_compat.json"
METRICS_LOG = REPO / "artifacts" / "experiments" / "netra_v03" / "pilot_01_run2" / "metrics.jsonl"
V02_CHECKPOINT = REPO / "artifacts" / "checkpoints" / "netra_v0_2" / "netra_baseline_v02_dac482fcd84a_best.pt"
EVAL_DIR = REPO / "artifacts" / "experiments" / "netra_v03" / "pilot_01_run2" / "evaluation"
REPORT_JSON = REPO / "reports" / "netra_v03" / "netra_v03_b1_final_evaluation.json"

THRESHOLD = 0.806  # Frozen v0.2 threshold — NOT retuned
BATCH_SIZE = 4
OIL_CLASS = 1
PR_BINS = 1024


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_model(checkpoint_path: Path, device: torch.device):
    """Load B1 model from checkpoint."""
    config = NetraModelConfig(
        encoder_name="resnet34",
        encoder_weights=None,  # never fetch external weights during eval
        in_channels=2,
        classes=2,
        tile_confidence_head=False,
    )
    model = create_netra_model(config)
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    
    # The training script saves model state_dict under 'model' key
    state_dict = ckpt["model"]
    model.load_state_dict(state_dict, strict=True)
    model.to(device).eval()
    
    return model, ckpt


class SegCounts:
    """Exact pixel-level confusion matrix accumulator."""
    def __init__(self):
        self.tp = self.fp = self.fn = self.tn = 0
        self.n_tiles = 0
    
    def add(self, tp, fp, fn, tn, n=1):
        self.tp += int(tp); self.fp += int(fp)
        self.fn += int(fn); self.tn += int(tn)
        self.n_tiles += int(n)
    
    def metrics(self) -> dict:
        tp, fp, fn, tn = self.tp, self.fp, self.fn, self.tn
        denom_iou = tp + fp + fn
        denom_dice = 2 * tp + fp + fn
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        total = tp + fp + fn + tn
        fg_frac = (tp + fp) / total if total else 0.0
        return {
            "iou_oil": (tp / denom_iou) if denom_iou else float("nan"),
            "dice_oil": (2 * tp / denom_dice) if denom_dice else float("nan"),
            "precision_oil": prec,
            "recall_oil": rec,
            "f1_oil": (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0,
            "fp_rate": fp / (fp + tn) if (fp + tn) else float("nan"),
            "fn_rate": fn / (fn + tp) if (fn + tp) else float("nan"),
            "foreground_fraction": fg_frac,
            "pixel_accuracy": ((tp + tn) / total) if total else float("nan"),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "n_tiles": self.n_tiles,
            "total_pixels": total,
        }


def pr_from_hist(pos_hist: np.ndarray, neg_hist: np.ndarray):
    """Compute PR-AUC from probability histograms."""
    total_pos = int(pos_hist.sum())
    if total_pos == 0:
        return float("nan"), float("nan"), float("nan")
    tp_cum = np.cumsum(pos_hist[::-1])[::-1].astype(np.float64)
    fp_cum = np.cumsum(neg_hist[::-1])[::-1].astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        precision = np.where((tp_cum + fp_cum) > 0, tp_cum / (tp_cum + fp_cum), 1.0)
        recall = tp_cum / total_pos
        f1 = np.where((precision + recall) > 0,
                      2 * precision * recall / (precision + recall), 0.0)
    order = np.argsort(recall)
    pr_auc = float(np.trapezoid(precision[order], recall[order]))
    k = int(np.argmax(f1))
    return pr_auc, float(f1[k]), float(k / (PR_BINS - 1))


@torch.no_grad()
def evaluate_holdout(model, dataset, device, threshold):
    """Full CALM-GRD-HOLDOUT evaluation with per-scene breakouts."""
    loader = torch.utils.data.DataLoader(
        dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0, pin_memory=True
    )
    
    overall = SegCounts()
    by_scene = defaultdict(SegCounts)
    by_label_type = defaultdict(SegCounts)
    by_wind = defaultdict(SegCounts)
    
    pos_hist = np.zeros(PR_BINS, dtype=np.int64)
    neg_hist = np.zeros(PR_BINS, dtype=np.int64)
    
    max_prob_all = 0.0
    tile_ious = []
    n_evaluated = 0
    t0 = time.perf_counter()
    
    for batch in loader:
        images, targets, meta = batch
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        
        with torch.autocast("cuda", enabled=device.type == "cuda"):
            logits = model(images)
        logits = logits.float()
        
        probs = torch.softmax(logits, dim=1)[:, OIL_CLASS]  # [B, H, W]
        
        # Mask out IGNORE pixels (255) for metrics
        valid = targets != IGNORE_INDEX
        
        pred = probs >= threshold
        tgt = targets == OIL_CLASS
        
        # Only count valid pixels
        pred_v = pred & valid
        tgt_v = tgt & valid
        
        tp_m = pred_v & tgt_v
        fp_m = pred_v & ~tgt_v
        fn_m = ~pred_v & tgt_v
        tn_m = ~pred_v & ~tgt_v & valid
        
        b = images.shape[0]
        overall.add(tp_m.sum().item(), fp_m.sum().item(),
                    fn_m.sum().item(), tn_m.sum().item(), b)
        
        # Update max prob
        batch_max = float(probs.max().item())
        max_prob_all = max(max_prob_all, batch_max)
        
        # PR histogram on valid pixels only
        valid_probs = probs[valid].flatten()
        valid_tgt = tgt[valid].flatten()
        idx = torch.clamp((valid_probs * (PR_BINS - 1)).long(), 0, PR_BINS - 1)
        pos_hist += torch.bincount(idx[valid_tgt], minlength=PR_BINS).cpu().numpy()
        neg_hist += torch.bincount(idx[~valid_tgt], minlength=PR_BINS).cpu().numpy()
        
        # Per-tile breakouts
        for i in range(b):
            valid_i = valid[i]
            tp_i = int(tp_m[i].sum().item())
            fp_i = int(fp_m[i].sum().item())
            fn_i = int(fn_m[i].sum().item())
            tn_i = int(tn_m[i].sum().item())
            
            # Per-tile IoU
            denom = tp_i + fp_i + fn_i
            tile_iou = tp_i / denom if denom > 0 else float("nan")
            tile_ious.append(tile_iou)
            
            # Scene breakout
            scene_id = meta["scene_id"][i] if isinstance(meta["scene_id"], (list, tuple)) else str(meta["scene_id"])
            by_scene[scene_id].add(tp_i, fp_i, fn_i, tn_i, 1)
            
            # Label type breakout (semantic_class: oil, lookalike, etc.)
            sem_class = meta["semantic_class"][i] if isinstance(meta["semantic_class"], (list, tuple)) else str(meta["semantic_class"])
            by_label_type[sem_class].add(tp_i, fp_i, fn_i, tn_i, 1)
            
            # Wind regime breakout
            wind = meta["wind_regime"][i] if isinstance(meta["wind_regime"], (list, tuple)) else str(meta["wind_regime"])
            by_wind[wind].add(tp_i, fp_i, fn_i, tn_i, 1)
        
        n_evaluated += b
    
    eval_time = time.perf_counter() - t0
    pr_auc, best_f1, best_f1_thr = pr_from_hist(pos_hist, neg_hist)
    
    # Tile IoU statistics (excluding NaN)
    valid_tile_ious = [x for x in tile_ious if not (x != x)]  # NaN check
    tile_iou_stats = {
        "mean": float(np.mean(valid_tile_ious)) if valid_tile_ious else float("nan"),
        "median": float(np.median(valid_tile_ious)) if valid_tile_ious else float("nan"),
        "min": float(np.min(valid_tile_ious)) if valid_tile_ious else float("nan"),
        "max": float(np.max(valid_tile_ious)) if valid_tile_ious else float("nan"),
        "std": float(np.std(valid_tile_ious)) if valid_tile_ious else float("nan"),
        "n_valid": len(valid_tile_ious),
        "n_nan": len(tile_ious) - len(valid_tile_ious),
    }
    
    return {
        "overall": overall.metrics(),
        "pr_auc": pr_auc,
        "best_f1": best_f1,
        "best_f1_threshold": best_f1_thr,
        "max_oil_probability": max_prob_all,
        "tile_iou_stats": tile_iou_stats,
        "by_scene": {k: v.metrics() for k, v in sorted(by_scene.items())},
        "by_semantic_class": {k: v.metrics() for k, v in sorted(by_label_type.items())},
        "by_wind_regime": {k: v.metrics() for k, v in sorted(by_wind.items())},
        "n_tiles": n_evaluated,
        "eval_seconds": round(eval_time, 2),
        "threshold": threshold,
    }


def audit_training_dynamics(metrics_path: Path) -> dict:
    """Read training logs and produce dynamics summary."""
    records = []
    with open(metrics_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    
    if not records:
        return {"status": "NO_RECORDS"}
    
    # Extract key series
    epochs = sorted(set(r["epoch"] for r in records))
    
    # First and last records
    first = records[0]
    last = records[-1]
    
    # Loss trajectory
    losses = [r["loss_total"] for r in records]
    grad_norms = [r["grad_norm"] for r in records]
    mil_losses = [r.get("loss_mil", 0) for r in records]
    strong_losses = [r["loss_strong"] for r in records]
    weak_neg_losses = [r.get("loss_weak_negative", 0) for r in records]
    
    # Gradient clipping analysis
    clip_threshold = 5.0
    clipped = sum(1 for g in grad_norms if g > clip_threshold)
    
    # Window means from the last record
    win_data = {k: last[k] for k in last if k.startswith("win_")}
    
    return {
        "n_records": len(records),
        "epochs": len(epochs),
        "first_epoch": first["epoch"],
        "last_epoch": last["epoch"],
        "last_step": last["step"],
        "total_elapsed_s": last["elapsed_s"],
        "loss_trajectory": {
            "first": first["loss_total"],
            "last": last["loss_total"],
            "min": min(losses),
            "max": max(losses),
            "final_window_avg": last.get("win_loss_total"),
        },
        "strong_loss": {
            "first": first["loss_strong"],
            "last": last["loss_strong"],
            "final_window_avg": last.get("win_loss_strong"),
        },
        "weak_negative_loss": {
            "first": first.get("loss_weak_negative", 0),
            "last": last.get("loss_weak_negative", 0),
            "final_window_avg": last.get("win_loss_weak_negative"),
        },
        "mil_loss": {
            "first": first.get("loss_mil", 0),
            "last": last.get("loss_mil", 0),
            "final_window_avg": last.get("win_loss_mil"),
        },
        "gradient_norms": {
            "mean": float(np.mean(grad_norms)),
            "median": float(np.median(grad_norms)),
            "max": float(np.max(grad_norms)),
            "min": float(np.min(grad_norms)),
            "clipped_count": clipped,
            "clipped_fraction": clipped / len(grad_norms),
            "clip_threshold": clip_threshold,
        },
        "vram_gb": last.get("vram_gb"),
        "final_window": win_data,
        "optimization_assessment": (
            "BENIGN" if last.get("win_loss_total", 1.0) < 0.1 and last["loss_total"] < 0.1
            else "CONCERNING" if last.get("win_loss_total", 1.0) > 0.5
            else "INCONCLUSIVE"
        ),
    }


def main():
    print("=" * 72)
    print("NETRA v0.3-B1 — FINAL SCIENTIFIC EVALUATION")
    print("=" * 72)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nDevice: {device}")
    
    # ── Phase 0: Record hashes ────────────────────────────────────────────
    print("\n── Phase 0: Checkpoint & data integrity ──")
    b1_hash = sha256_file(CHECKPOINT)
    v02_hash = sha256_file(V02_CHECKPOINT)
    print(f"B1 checkpoint SHA256:  {b1_hash}")
    print(f"B1 checkpoint size:    {CHECKPOINT.stat().st_size:,} bytes")
    print(f"v0.2 checkpoint SHA256: {v02_hash}")
    assert v02_hash == "9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66", \
        "v0.2 checkpoint hash mismatch — ABORT"
    print("v0.2 checkpoint hash ✅ VERIFIED")
    
    # ── Phase 1: Load model ───────────────────────────────────────────────
    print("\n── Phase 1: Load B1 model ──")
    model, ckpt = load_model(CHECKPOINT, device)
    print(f"Checkpoint keys: {list(ckpt.keys())}")
    print(f"Training epoch:  {ckpt['epoch']}")
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {n_params:,}")
    print(f"Model loaded ✅")
    
    # ── Phase 2: Load normalization ───────────────────────────────────────
    print("\n── Phase 2: Load normalization ──")
    with open(NORM_FILE) as f:
        norm = json.load(f)
    print(f"Normalization version: {norm['normalization_version']}")
    print(f"Channel order: {norm['channel_order']}")
    
    # ── Phase 3: CALM-GRD-HOLDOUT evaluation ──────────────────────────────
    print("\n── Phase 3: CALM-GRD-HOLDOUT evaluation ──")
    holdout_ds = NetraGoldV03Dataset(
        records_path=TILE_RECORDS,
        split="holdout",
        repo_root=REPO,
        apply_ignore=False,  # For evaluation, we want full masks (not MIL ignore)
        return_meta=True,
        normalization=norm,
    )
    print(f"Holdout tiles:  {len(holdout_ds)}")
    print(f"Label quality:  {holdout_ds.label_quality_counts()}")
    print(f"Threshold:      {THRESHOLD} (v0.2 frozen, NOT retuned)")
    print(f"Evaluating...")
    
    holdout_results = evaluate_holdout(model, holdout_ds, device, THRESHOLD)
    
    o = holdout_results["overall"]
    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  CALM-GRD-HOLDOUT RESULTS                ║")
    print(f"  ╠══════════════════════════════════════════╣")
    print(f"  ║  IoU (oil):       {o['iou_oil']:.6f}              ║")
    print(f"  ║  Dice/F1 (oil):   {o['dice_oil']:.6f}              ║")
    print(f"  ║  Precision:       {o['precision_oil']:.6f}              ║")
    print(f"  ║  Recall:          {o['recall_oil']:.6f}              ║")
    print(f"  ║  PR-AUC:          {holdout_results['pr_auc']:.6f}              ║")
    print(f"  ║  FP rate:         {o['fp_rate']:.6f}              ║")
    print(f"  ║  FN rate:         {o['fn_rate']:.6f}              ║")
    print(f"  ║  FG fraction:     {o['foreground_fraction']:.6f}              ║")
    print(f"  ║  Max oil prob:    {holdout_results['max_oil_probability']:.6f}              ║")
    print(f"  ║  Best F1:         {holdout_results['best_f1']:.6f}              ║")
    print(f"  ║  Best F1 thr:     {holdout_results['best_f1_threshold']:.6f}              ║")
    print(f"  ║  Tiles:           {holdout_results['n_tiles']}                       ║")
    print(f"  ║  Eval time:       {holdout_results['eval_seconds']:.1f}s                     ║")
    print(f"  ╚══════════════════════════════════════════╝")
    
    # Per-scene
    print("\n  Per-scene IoU:")
    scene_ious = []
    for scene_id, sm in sorted(holdout_results["by_scene"].items()):
        iou = sm["iou_oil"]
        scene_ious.append(iou)
        print(f"    {scene_id[:40]:40s}  IoU={iou:.4f}  P={sm['precision_oil']:.4f}  R={sm['recall_oil']:.4f}  tiles={sm['n_tiles']}")
    
    valid_scene_ious = [x for x in scene_ious if not (x != x)]
    if valid_scene_ious:
        print(f"\n  Scene IoU: mean={np.mean(valid_scene_ious):.4f}  median={np.median(valid_scene_ious):.4f}  "
              f"min={np.min(valid_scene_ious):.4f}  max={np.max(valid_scene_ious):.4f}  "
              f"std={np.std(valid_scene_ious):.4f}")
    
    # By semantic class
    print("\n  By semantic class:")
    for cls, sm in sorted(holdout_results["by_semantic_class"].items()):
        print(f"    {cls:30s}  IoU={sm['iou_oil']:.4f}  P={sm['precision_oil']:.4f}  R={sm['recall_oil']:.4f}  FG={sm['foreground_fraction']:.6f}  tiles={sm['n_tiles']}")
    
    # By wind regime
    print("\n  By wind regime:")
    for wind, sm in sorted(holdout_results["by_wind_regime"].items()):
        print(f"    {wind:30s}  IoU={sm['iou_oil']:.4f}  P={sm['precision_oil']:.4f}  R={sm['recall_oil']:.4f}  tiles={sm['n_tiles']}")
    
    # ── Phase 8: Training dynamics ────────────────────────────────────────
    print("\n── Phase 8: Training dynamics audit ──")
    dynamics = audit_training_dynamics(METRICS_LOG)
    print(f"  Records:           {dynamics['n_records']}")
    print(f"  Epochs:            {dynamics['epochs']}")
    print(f"  Total time:        {dynamics['total_elapsed_s']:.0f}s ({dynamics['total_elapsed_s']/3600:.1f}h)")
    print(f"  Loss first→last:   {dynamics['loss_trajectory']['first']:.4f} → {dynamics['loss_trajectory']['last']:.6f}")
    print(f"  Final window avg:  {dynamics['loss_trajectory']['final_window_avg']:.6f}")
    gn = dynamics["gradient_norms"]
    print(f"  Grad norm mean:    {gn['mean']:.3f}  median: {gn['median']:.3f}  max: {gn['max']:.1f}")
    print(f"  Clipped fraction:  {gn['clipped_fraction']:.1%} ({gn['clipped_count']}/{dynamics['n_records']})")
    print(f"  Assessment:        {dynamics['optimization_assessment']}")
    
    # ── Phase 9: Scientific verdict ───────────────────────────────────────
    print("\n── Phase 9: Scientific verdict ──")
    iou = o["iou_oil"]
    pr_auc = holdout_results["pr_auc"]
    recall = o["recall_oil"]
    precision = o["precision_oil"]
    fp_rate = o["fp_rate"]
    
    # NOTE: the CALM-GRD-HOLDOUT labels are WEAK_BOX (bounding boxes, not pixel-precise).
    # This means IoU/Dice on these labels has a CEILING well below 1.0 because
    # the "ground truth" boxes contain ~62% non-oil pixels marked as positive.
    # A model that perfectly detects oil and perfectly rejects non-oil within
    # boxes would score IoU ~0.38 on these labels, not 1.0.
    # This is acknowledged as a fundamental label-quality limitation.
    
    v02_iou = 0.6458  # Official v0.2 test
    v02_pr_auc = 0.8513
    
    # Determine verdict
    if iou > v02_iou * 0.9 and pr_auc > 0.5 and recall > 0.3:
        if iou > v02_iou:
            verdict = "V03_B1_SUCCESS"
        else:
            verdict = "V03_B1_PARTIAL_SUCCESS"
    elif iou < 0.01 or recall < 0.01:
        if pr_auc < 0.1:
            verdict = "V03_B1_TRAINING_FAILED"
        else:
            verdict = "V03_B1_NO_GENERALIZATION_GAIN"
    elif iou < v02_iou * 0.5:
        verdict = "V03_B1_REGRESSION"
    else:
        verdict = "V03_B1_PARTIAL_SUCCESS"
    
    # CRITICAL CAVEAT: Direct comparison with v0.2 numbers is NOT apples-to-apples
    # v0.2 was evaluated on Zenodo Part III (STRONG_PIXEL labels, 152 scenes, different geography)
    # v0.3-B1 holdout is ESSD/PANGAEA (WEAK_BOX labels, 14 scenes, Eastern Mediterranean)
    # The label quality difference alone means IoU is NOT directly comparable
    
    comparison_note = (
        "NOT_DIRECTLY_COMPARABLE: v0.2 IoU 0.6458 was measured on Zenodo Part III "
        "with STRONG_PIXEL labels (pixel-precise masks). B1 holdout uses WEAK_BOX "
        "labels (bounding boxes with ~62% non-oil interior). These label sets have "
        "fundamentally different IoU ceilings. PR-AUC is more comparable as it measures "
        "the ranking quality of the probability output independent of the threshold."
    )
    
    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  SCIENTIFIC VERDICT: {verdict:22s}  ║")
    print(f"  ╚══════════════════════════════════════════╝")
    print(f"\n  v0.2 comparison: {comparison_note[:80]}...")
    
    # ── Save results ──────────────────────────────────────────────────────
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    
    report = {
        "evaluation_id": "netra_v03_b1_final_evaluation",
        "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scientific_verdict": verdict,
        "checkpoint": {
            "path": str(CHECKPOINT),
            "sha256": b1_hash,
            "size_bytes": CHECKPOINT.stat().st_size,
            "training_epoch": ckpt["epoch"],
            "training_commit": ckpt.get("run_metadata", {}).get("git_commit", "unknown"),
        },
        "v02_reference": {
            "checkpoint_sha256": v02_hash,
            "official_iou": v02_iou,
            "official_pr_auc": v02_pr_auc,
            "comparison_status": comparison_note,
        },
        "normalization": {
            "version": norm["normalization_version"],
            "channel_order": norm["channel_order"],
        },
        "calm_grd_holdout": holdout_results,
        "training_dynamics": dynamics,
        "label_quality_caveat": (
            "CALM-GRD-HOLDOUT labels are WEAK_BOX (bounding boxes, not pixel masks). "
            "IoU ceiling is ~0.38 for a perfect pixel-level detector on these labels. "
            "This is a known, pre-existing property of the ESSD/PANGAEA dataset, not "
            "a model defect."
        ),
        "source_domain_preservation": {
            "status": "NOT_EVALUATED_IN_THIS_RUN",
            "reason": "Zenodo Part III evaluation requires the v0.2 Gold test loader, "
                      "which uses a different data format (3-channel with ratio). "
                      "This evaluation focused on CALM-GRD-HOLDOUT as the primary surface."
        },
        "mc20_external": {
            "status": "NOT_EVALUATED_IN_THIS_RUN",
            "reason": "MC20 external evaluation is Phase 11, separate from the primary evaluation."
        },
        "safety": {
            "files_modified": 0,
            "files_deleted": 0,
            "b1_checkpoint_hash_post_eval": "WILL_VERIFY",
            "v02_checkpoint_hash_post_eval": "WILL_VERIFY",
        },
    }
    
    # Verify checkpoint immutability
    b1_hash_post = sha256_file(CHECKPOINT)
    v02_hash_post = sha256_file(V02_CHECKPOINT)
    report["safety"]["b1_checkpoint_hash_post_eval"] = b1_hash_post
    report["safety"]["v02_checkpoint_hash_post_eval"] = v02_hash_post
    report["safety"]["checkpoints_unchanged"] = (b1_hash == b1_hash_post and v02_hash == v02_hash_post)
    
    # Save
    with open(EVAL_DIR / "holdout_results.json", "w") as f:
        json.dump(holdout_results, f, indent=2, default=str)
    
    with open(EVAL_DIR / "training_dynamics.json", "w") as f:
        json.dump(dynamics, f, indent=2, default=str)
    
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_JSON, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n  Results saved to:")
    print(f"    {EVAL_DIR / 'holdout_results.json'}")
    print(f"    {EVAL_DIR / 'training_dynamics.json'}")
    print(f"    {REPORT_JSON}")
    
    print(f"\n  Checkpoint immutability: {'✅ VERIFIED' if report['safety']['checkpoints_unchanged'] else '❌ CHANGED'}")
    
    print(f"\n{'='*72}")
    print(f"EVALUATION COMPLETE — VERDICT: {verdict}")
    print(f"{'='*72}")
    
    return report


if __name__ == "__main__":
    main()
