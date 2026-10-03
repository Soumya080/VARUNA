"""
NETRA segmentation losses (Phase 18).

Replaces the M5 stubs that returned the constants 0.5 / 1.0 regardless of input.
Every value returned here is computed from the logits and targets passed in.

The NETRA baseline faces roughly 3% positive pixels with a large fraction of
entirely-empty tiles, so plain cross-entropy collapses to background. The
default is soft-Dice on the OIL class combined with cross-entropy.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

OIL_CLASS = 1


class DiceLoss(nn.Module):
    """Soft Dice over the foreground (OIL) class.

    Args:
        smooth: Laplace term keeping the ratio finite when a batch has no
            positive pixels in either prediction or target.
        ignore_empty: when True, batches whose target contains no positive
            pixel contribute 0 rather than a saturated 1 - smooth/smooth term.
    """

    def __init__(self, smooth: float = 1.0, ignore_empty: bool = False) -> None:
        super().__init__()
        self.smooth = float(smooth)
        self.ignore_empty = bool(ignore_empty)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # logits [B,C,H,W]; targets [B,H,W] int64
        probs = torch.softmax(logits.float(), dim=1)[:, OIL_CLASS]      # [B,H,W]
        tgt = (targets == OIL_CLASS).to(probs.dtype)                     # [B,H,W]

        dims = (1, 2)
        inter = (probs * tgt).sum(dims)
        denom = probs.sum(dims) + tgt.sum(dims)
        dice = (2.0 * inter + self.smooth) / (denom + self.smooth)
        loss = 1.0 - dice                                                # [B]

        if self.ignore_empty:
            keep = tgt.sum(dims) > 0
            if not keep.any():
                return logits.sum() * 0.0
            loss = loss[keep]
        return loss.mean()


class CombinedLoss(nn.Module):
    """`dice_weight * Dice(OIL) + ce_weight * CrossEntropy`.

    `class_weights` is applied to the cross-entropy term only; it is the
    conventional lever for the 30:1 background/oil pixel ratio measured on
    this corpus.
    """

    def __init__(
        self,
        class_weights: list[float] | None = None,
        dice_weight: float = 0.5,
        ce_weight: float = 0.5,
        smooth: float = 1.0,
        ignore_empty_dice: bool = False,
    ) -> None:
        super().__init__()
        self.dice = DiceLoss(smooth=smooth, ignore_empty=ignore_empty_dice)
        self.dice_weight = float(dice_weight)
        self.ce_weight = float(ce_weight)
        if class_weights is not None:
            self.register_buffer(
                "class_weights", torch.tensor(class_weights, dtype=torch.float32)
            )
        else:
            self.class_weights = None

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        w = self.class_weights
        if w is not None:
            w = w.to(device=logits.device, dtype=torch.float32)
        ce = F.cross_entropy(logits.float(), targets, weight=w)
        dc = self.dice(logits, targets)
        return self.ce_weight * ce + self.dice_weight * dc

    def components(self, logits: torch.Tensor, targets: torch.Tensor) -> dict[str, float]:
        """Per-term breakdown, for logging. Not used in the backward path."""
        with torch.no_grad():
            w = self.class_weights
            if w is not None:
                w = w.to(device=logits.device, dtype=torch.float32)
            ce = F.cross_entropy(logits.float(), targets, weight=w)
            dc = self.dice(logits, targets)
        return {"ce": float(ce.item()), "dice": float(dc.item())}


def build_loss(
    name: str = "dice_ce",
    class_weights: list[float] | None = None,
    dice_weight: float = 0.5,
    ce_weight: float = 0.5,
) -> nn.Module:
    name = name.lower()
    if name in ("dice_ce", "combined"):
        return CombinedLoss(
            class_weights=class_weights, dice_weight=dice_weight, ce_weight=ce_weight
        )
    if name == "dice":
        return DiceLoss()
    if name in ("ce", "cross_entropy"):
        w = torch.tensor(class_weights, dtype=torch.float32) if class_weights else None

        class _CE(nn.Module):
            def __init__(self, weight):
                super().__init__()
                if weight is not None:
                    self.register_buffer("w", weight)
                else:
                    self.w = None

            def forward(self, logits, targets):
                w = self.w.to(logits.device) if self.w is not None else None
                return F.cross_entropy(logits.float(), targets, weight=w)

        return _CE(w)
    raise ValueError(f"unknown loss {name!r}")
