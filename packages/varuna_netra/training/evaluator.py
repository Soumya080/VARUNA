"""
NETRA evaluator (Phase 20).

Replaces the M5 stub that returned `iou_oil=0.75, dice_oil=0.80, f1_oil=0.82,
ood_auroc=0.92` regardless of the model. Every number below is accumulated
from real model predictions against real labels.

Design notes
------------
* Counts are accumulated as int64 confusion-matrix entries over pixels, so the
  evaluator is exact and streams in constant memory.
* PR-AUC is computed from a 1024-bin histogram of the OIL probability, split by
  true label. This avoids materialising billions of per-pixel scores while
  still producing a faithful curve.
* Metrics are reported for the whole split and broken out by tile population
  (positive vs empty) and by source dataset, because false positives on the
  Part II hard negatives are the headline risk for this model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import torch

OIL_CLASS = 1
PR_BINS = 1024


@dataclass
class SegCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    n_tiles: int = 0

    def add(self, tp: int, fp: int, fn: int, tn: int, n_tiles: int = 0) -> None:
        self.tp += int(tp)
        self.fp += int(fp)
        self.fn += int(fn)
        self.tn += int(tn)
        self.n_tiles += int(n_tiles)

    def metrics(self) -> dict[str, float]:
        tp, fp, fn, tn = self.tp, self.fp, self.fn, self.tn
        denom_iou = tp + fp + fn
        denom_dice = 2 * tp + fp + fn
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        total = tp + fp + fn + tn
        return {
            "iou_oil": (tp / denom_iou) if denom_iou else float("nan"),
            "dice_oil": (2 * tp / denom_dice) if denom_dice else float("nan"),
            "precision_oil": prec,
            "recall_oil": rec,
            "f1_oil": (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0,
            "pixel_accuracy": ((tp + tn) / total) if total else float("nan"),
            "fp_pixel_rate": (fp / (fp + tn)) if (fp + tn) else float("nan"),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "n_tiles": self.n_tiles,
        }


@dataclass
class NetraSegMetrics:
    split: str
    threshold: float
    n_tiles: int
    n_pixels: int
    overall: dict[str, float]
    by_population: dict[str, dict[str, float]] = field(default_factory=dict)
    by_source: dict[str, dict[str, float]] = field(default_factory=dict)
    confusion_matrix: list[list[int]] = field(default_factory=list)
    pr_auc: float = float("nan")
    best_f1: float = float("nan")
    best_f1_threshold: float = float("nan")
    loss: float = float("nan")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NetraEvaluator:
    """Computes segmentation metrics from actual model outputs."""

    def __init__(self, threshold: float = 0.5, amp: bool = True) -> None:
        self.threshold = float(threshold)
        self.amp = bool(amp)

    @torch.no_grad()
    def evaluate(
        self,
        model: Any,
        loader: Any,
        device: str | torch.device = "cuda",
        loss_fn: Any = None,
        split: str = "val",
        threshold: float | None = None,
    ) -> NetraSegMetrics:
        thr = self.threshold if threshold is None else float(threshold)
        device = torch.device(device)
        model.eval()
        model.to(device)

        overall = SegCounts()
        by_pop: dict[str, SegCounts] = {"positive_tiles": SegCounts(), "empty_tiles": SegCounts()}
        by_src: dict[str, SegCounts] = {}

        pos_hist = np.zeros(PR_BINS, dtype=np.int64)   # OIL-prob histogram for true-positive pixels
        neg_hist = np.zeros(PR_BINS, dtype=np.int64)   # OIL-prob histogram for true-negative pixels

        loss_sum, loss_batches, n_pixels = 0.0, 0, 0

        for batch in loader:
            if len(batch) == 3:
                images, masks, meta = batch
            else:
                images, masks = batch
                meta = None

            images = images.to(device, non_blocking=True)
            masks = masks.to(device, non_blocking=True)

            with torch.autocast("cuda", enabled=self.amp and device.type == "cuda"):
                logits = model(images)
            logits = logits.float()

            if loss_fn is not None:
                loss_sum += float(loss_fn(logits, masks).item())
                loss_batches += 1

            probs = torch.softmax(logits, dim=1)[:, OIL_CLASS]      # [B,H,W]
            pred = probs >= thr
            tgt = masks == OIL_CLASS

            tp_m = pred & tgt
            fp_m = pred & ~tgt
            fn_m = ~pred & tgt
            tn_m = ~pred & ~tgt

            b = images.shape[0]
            n_pixels += int(tgt.numel())
            overall.add(tp_m.sum().item(), fp_m.sum().item(), fn_m.sum().item(),
                        tn_m.sum().item(), b)

            # per-tile breakouts
            per_tile_tp = tp_m.flatten(1).sum(1)
            per_tile_fp = fp_m.flatten(1).sum(1)
            per_tile_fn = fn_m.flatten(1).sum(1)
            per_tile_tn = tn_m.flatten(1).sum(1)
            tile_has_oil = tgt.flatten(1).any(1)

            for i in range(b):
                key = "positive_tiles" if bool(tile_has_oil[i]) else "empty_tiles"
                by_pop[key].add(per_tile_tp[i].item(), per_tile_fp[i].item(),
                                per_tile_fn[i].item(), per_tile_tn[i].item(), 1)
                if meta is not None:
                    src = meta["source"][i] if isinstance(meta["source"], (list, tuple)) else str(meta["source"])
                    by_src.setdefault(src, SegCounts()).add(
                        per_tile_tp[i].item(), per_tile_fp[i].item(),
                        per_tile_fn[i].item(), per_tile_tn[i].item(), 1)

            # PR histogram
            idx = torch.clamp((probs * (PR_BINS - 1)).long(), 0, PR_BINS - 1)
            pos_hist += torch.bincount(idx[tgt].flatten(), minlength=PR_BINS).cpu().numpy()
            neg_hist += torch.bincount(idx[~tgt].flatten(), minlength=PR_BINS).cpu().numpy()

        pr_auc, best_f1, best_thr = self._pr_from_hist(pos_hist, neg_hist)
        o = overall.metrics()
        cm = [[overall.tn, overall.fp], [overall.fn, overall.tp]]

        return NetraSegMetrics(
            split=split,
            threshold=thr,
            n_tiles=overall.n_tiles,
            n_pixels=n_pixels,
            overall=o,
            by_population={k: v.metrics() for k, v in by_pop.items()},
            by_source={k: v.metrics() for k, v in sorted(by_src.items())},
            confusion_matrix=cm,
            pr_auc=pr_auc,
            best_f1=best_f1,
            best_f1_threshold=best_thr,
            loss=(loss_sum / loss_batches) if loss_batches else float("nan"),
        )

    @staticmethod
    def _pr_from_hist(pos_hist: np.ndarray, neg_hist: np.ndarray) -> tuple[float, float, float]:
        """Precision-recall curve by sweeping the threshold down the histogram."""
        total_pos = int(pos_hist.sum())
        if total_pos == 0:
            return float("nan"), float("nan"), float("nan")
        # cumulative from the top bin downwards == predicting positive at that threshold
        tp = np.cumsum(pos_hist[::-1])[::-1].astype(np.float64)
        fp = np.cumsum(neg_hist[::-1])[::-1].astype(np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            precision = np.where((tp + fp) > 0, tp / (tp + fp), 1.0)
            recall = tp / total_pos
            f1 = np.where((precision + recall) > 0,
                          2 * precision * recall / (precision + recall), 0.0)
        order = np.argsort(recall)
        pr_auc = float(np.trapezoid(precision[order], recall[order]))
        k = int(np.argmax(f1))
        return pr_auc, float(f1[k]), float(k / (PR_BINS - 1))
