"""
NETRA-GOLD-v0.2 | Post-baseline scientific audit, Phases 1-2.

Runs the FROZEN baseline checkpoint against the untouched 152-scene TEST
split, exactly once, at the already-calibrated threshold (0.806). This is
the official baseline test result.

Absolute rules honored here:
  - The checkpoint is opened read-only (torch.load) and never re-saved.
  - The test split is read via the manifest only (no glob).
  - No threshold search, no normalization refit, no augmentation happens
    against the test split. threshold=0.806 comes from the val-set sweep
    recorded in the frozen sidecar, computed before this script ever ran.
  - This script produces evidence; it does not retrain or tune anything.

Outputs:
  reports/netra_v02/07_official_test_eval.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import segmentation_models_pytorch as smp
import torch
from torch.utils.data import DataLoader

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "packages"))

from varuna_netra.dataset.gold import NetraGoldDataset, manifest_sha256  # noqa: E402
from varuna_netra.training.evaluator import OIL_CLASS, SegCounts  # noqa: E402
from varuna_netra.training.losses import build_loss  # noqa: E402

MANIFEST = REPO / "data" / "manifests" / "netra_gold_v0_2.json"
CKPT = REPO / "artifacts" / "checkpoints" / "netra_v0_2" / "netra_baseline_v02_dac482fcd84a_best.pt"
FROZEN = CKPT.with_name(CKPT.name + ".frozen.json")
OUT = REPO / "reports" / "netra_v02" / "07_official_test_eval.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collate_with_meta(batch):
    images = torch.stack([b[0] for b in batch])
    masks = torch.stack([b[1] for b in batch])
    metas = [b[2] for b in batch]
    meta = {k: [m[k] for m in metas] for k in metas[0]}
    return images, masks, meta


def phase1_checkpoint_integrity() -> dict:
    """PHASE 1 — checkpoint integrity, all [MEASURED]. Read-only."""
    result: dict = {"phase": "1_checkpoint_integrity"}
    result["checkpoint_path"] = str(CKPT)
    result["checkpoint_exists"] = CKPT.exists()
    if not CKPT.exists():
        result["status"] = "BLOCKED"
        return result

    result["checkpoint_sha256"] = sha256_of(CKPT)
    result["frozen_sidecar_path"] = str(FROZEN)
    result["frozen_sidecar_exists"] = FROZEN.exists()

    if FROZEN.exists():
        frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
        result["frozen_sidecar"] = frozen
        result["sha256_matches_sidecar"] = (
            frozen.get("checkpoint_sha256") == result["checkpoint_sha256"]
        )
    else:
        result["status"] = "BLOCKED"
        result["reason"] = "no frozen sidecar found"
        return result

    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    result["ckpt_epoch"] = ck.get("epoch")
    result["ckpt_best_metric"] = ck.get("best_metric")
    result["ckpt_dataset_version"] = ck.get("dataset_version")
    result["ckpt_manifest_hash"] = ck.get("manifest_hash")
    result["ckpt_normalization_version"] = ck.get("normalization_version")
    cfg = ck.get("config", {})
    result["ckpt_config"] = {
        k: cfg.get(k) for k in
        ("encoder_name", "encoder_weights", "in_channels", "classes",
         "gold_manifest", "dataset_version")
    }
    result["oil_class_index"] = OIL_CLASS
    result["calibrated_threshold"] = frozen.get("metrics", {}).get("best_f1_threshold")
    result["status"] = "PASS" if result["sha256_matches_sidecar"] else "FAIL"
    result["checkpoint_untouched"] = "verified byte-identical via sha256, no write performed"
    return result


def build_model(cfg: dict):
    return smp.Unet(
        encoder_name=cfg.get("encoder_name", "resnet34"),
        encoder_weights=None,  # never fetch weights during evaluation
        in_channels=int(cfg.get("in_channels", 2)),
        classes=int(cfg.get("classes", 2)),
    )


def phase2_official_test_eval(threshold: float, batch_size: int, num_workers: int) -> dict:
    """PHASE 2 — official, single-pass TEST evaluation. No tuning."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    model = build_model(ck.get("config", {}))
    model.load_state_dict(ck["model_state_dict"])
    model.to(device).eval()

    test_ds = NetraGoldDataset(MANIFEST, split="test", repo_root=REPO, return_meta=True)
    loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False,
                         num_workers=num_workers, pin_memory=True,
                         collate_fn=collate_with_meta)

    loss_fn = build_loss("dice_ce", class_weights=[1.0, 10.0])

    overall = SegCounts()
    by_pop = {"positive_tiles": SegCounts(), "empty_tiles": SegCounts()}
    by_src: dict[str, SegCounts] = {}
    by_scene: dict[str, SegCounts] = {}
    scene_source: dict[str, str] = {}

    PR_BINS = 1024
    pos_hist = np.zeros(PR_BINS, dtype=np.int64)
    neg_hist = np.zeros(PR_BINS, dtype=np.int64)

    loss_sum, loss_batches, n_pixels = 0.0, 0, 0
    t0 = time.perf_counter()

    with torch.no_grad():
        for images, masks, meta in loader:
            images = images.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)
            with torch.autocast("cuda", enabled=device.type == "cuda"):
                logits = model(images)
            logits = logits.float()
            loss_sum += float(loss_fn(logits, masks).item())
            loss_batches += 1

            probs = torch.softmax(logits, dim=1)[:, OIL_CLASS]
            pred = probs >= threshold
            tgt = masks == OIL_CLASS

            tp_m = pred & tgt
            fp_m = pred & ~tgt
            fn_m = ~pred & tgt
            tn_m = ~pred & ~tgt

            b = images.shape[0]
            n_pixels += int(tgt.numel())
            overall.add(tp_m.sum().item(), fp_m.sum().item(), fn_m.sum().item(),
                        tn_m.sum().item(), b)

            per_tp = tp_m.flatten(1).sum(1)
            per_fp = fp_m.flatten(1).sum(1)
            per_fn = fn_m.flatten(1).sum(1)
            per_tn = tn_m.flatten(1).sum(1)
            tile_has_oil = tgt.flatten(1).any(1)

            for i in range(b):
                key = "positive_tiles" if bool(tile_has_oil[i]) else "empty_tiles"
                by_pop[key].add(per_tp[i].item(), per_fp[i].item(), per_fn[i].item(), per_tn[i].item(), 1)

                src = meta["source"][i]
                by_src.setdefault(src, SegCounts()).add(
                    per_tp[i].item(), per_fp[i].item(), per_fn[i].item(), per_tn[i].item(), 1)

                scene = meta["scene_id"][i]
                scene_source[scene] = src
                by_scene.setdefault(scene, SegCounts()).add(
                    per_tp[i].item(), per_fp[i].item(), per_fn[i].item(), per_tn[i].item(), 1)

            idx = torch.clamp((probs * (PR_BINS - 1)).long(), 0, PR_BINS - 1)
            pos_hist += torch.bincount(idx[tgt].flatten(), minlength=PR_BINS).cpu().numpy()
            neg_hist += torch.bincount(idx[~tgt].flatten(), minlength=PR_BINS).cpu().numpy()

    elapsed = time.perf_counter() - t0

    # PR-AUC / best-F1 (reported for evidence only -- NOT used to pick the primary threshold)
    total_pos = int(pos_hist.sum())
    if total_pos > 0:
        tp_c = np.cumsum(pos_hist[::-1])[::-1].astype(np.float64)
        fp_c = np.cumsum(neg_hist[::-1])[::-1].astype(np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            precision = np.where((tp_c + fp_c) > 0, tp_c / (tp_c + fp_c), 1.0)
            recall = tp_c / total_pos
            f1 = np.where((precision + recall) > 0, 2 * precision * recall / (precision + recall), 0.0)
        order = np.argsort(recall)
        pr_auc = float(np.trapezoid(precision[order], recall[order]))
        k = int(np.argmax(f1))
        info_best_f1, info_best_thr = float(f1[k]), float(k / (PR_BINS - 1))
    else:
        pr_auc = info_best_f1 = info_best_thr = float("nan")

    result = {
        "phase": "2_official_test_evaluation",
        "primary_threshold_used": threshold,
        "threshold_source": "frozen sidecar best_f1_threshold from VAL-set sweep at epoch 32 "
                             "(no test-set threshold search performed)",
        "n_scenes": len(by_scene),
        "n_tiles": overall.n_tiles,
        "n_pixels": n_pixels,
        "elapsed_seconds": elapsed,
        "loss": loss_sum / loss_batches if loss_batches else float("nan"),
        "overall": overall.metrics(),
        "confusion_matrix": {"tn": overall.tn, "fp": overall.fp, "fn": overall.fn, "tp": overall.tp},
        "by_population": {k: v.metrics() for k, v in by_pop.items()},
        "by_source": {k: v.metrics() for k, v in sorted(by_src.items())},
        "pr_auc": pr_auc,
        "info_only_best_f1": info_best_f1,
        "info_only_best_f1_threshold": info_best_thr,
        "info_only_note": "best_f1/threshold above are reported as evidence about the test "
                           "distribution only. The primary result uses the pre-registered "
                           "val-calibrated threshold (0.806); this is NOT a re-calibration.",
        "per_scene": {
            scene: {**by_scene[scene].metrics(), "source": scene_source[scene]}
            for scene in sorted(by_scene)
        },
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.806)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--num-workers", type=int, default=4)
    args = ap.parse_args()

    print("=" * 70)
    print(" PHASE 1: CHECKPOINT INTEGRITY")
    print("=" * 70)
    p1 = phase1_checkpoint_integrity()
    for k, v in p1.items():
        if k not in ("frozen_sidecar",):
            print(f"  {k}: {v}")
    if p1.get("status") != "PASS":
        print("CHECKPOINT INTEGRITY FAILED -- aborting before touching the test set.")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"phase1": p1}, indent=2), encoding="utf-8")
        return 1

    print()
    print("=" * 70)
    print(" PHASE 2: OFFICIAL TEST EVALUATION (152 scenes, single pass)")
    print("=" * 70)
    p2 = phase2_official_test_eval(args.threshold, args.batch_size, args.num_workers)
    o = p2["overall"]
    print(f"  n_scenes={p2['n_scenes']} n_tiles={p2['n_tiles']} n_pixels={p2['n_pixels']}")
    print(f"  threshold={p2['primary_threshold_used']}")
    print(f"  IoU={o['iou_oil']:.4f} Dice/F1={o['dice_oil']:.4f} "
          f"P={o['precision_oil']:.4f} R={o['recall_oil']:.4f} PR-AUC={p2['pr_auc']:.4f}")
    print(f"  confusion_matrix: {p2['confusion_matrix']}")
    print(f"  by_population: {json.dumps(p2['by_population'], indent=2)}")
    print(f"  by_source: {json.dumps(p2['by_source'], indent=2)}")
    print(f"  elapsed: {p2['elapsed_seconds']:.1f}s")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"phase1": p1, "phase2": p2}, indent=2), encoding="utf-8")
    print(f"\nwrote -> {OUT}")
    print("\nTEST_SET_STATUS = LOCKED_FOR_FINAL_EVALUATION")
    print("This split has now been read exactly once for the official result.")
    print("It must not be used for model selection, threshold tuning, or further comparisons")
    print("without treating any additional read as a second official evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
