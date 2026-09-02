"""NETRA v0.3 weak-supervision loss (MIL over annotation boxes).

WHY THIS EXISTS
    ESSD/PANGAEA supplies real oil-object bounding boxes but zero
    pixel-level masks. Feeding box interiors to a pixelwise loss as
    positives would be fabrication (~62.3% of box interior is measured
    not-plausibly-oil). Feeding them as IGNORE gives ESSD only negative
    signal, which -- combined with P(positive|ESSD)=0 -- lets the model
    minimise loss by learning "new domain => background", the opposite
    of the domain-generalisation goal.

WHAT THE ANNOTATION ACTUALLY ASSERTS
    "An oil OBJECT exists inside this box."
    Not "every pixel here is oil", and not merely "one pixel here is
    oil" -- an object occupies many contiguous pixels.

POOLING CHOICE (measured, see reports/netra_v03/WEAK_SUPERVISION_FORMULATION_REPORT.md)
    Real box sizes span 144 - 248,320 px (1,700x). Across that range:
      noisy-OR : saturates to 1.000 even on PURE NOISE -> cannot
                 distinguish oil from nothing. Rejected.
      LSE      : pooled value grows with box size (5.0 -> 12.5); noise
                 and object differ by 0.06. Rejected.
      hard max : a single pathological pixel scores 0.990, HIGHER than a
                 genuine object at 0.900 -> trivially exploitable.
                 Rejected.
      top-k    : one hot pixel is indistinguishable from noise
                 (0.095 vs 0.095); a real object scores ~5x higher;
                 stable across sizes. SELECTED.

    top-k mean with k = max(kmin, frac * |B|) encodes "a meaningful
    number of pixels in this box are oil", which is what an object is.
    It never asserts WHICH pixels -- the model chooses them.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

OIL_CLASS = 1
IGNORE_INDEX = 255

# Sample-type tags. Kept explicit so weak samples can never be silently
# coerced into strong-label semantics (or vice versa).
STRONG_PIXEL = "STRONG_PIXEL"
WEAK_BOX_OIL = "WEAK_BOX_OIL"
NEGATIVE_OR_LOOKALIKE = "NEGATIVE_OR_LOOKALIKE"


def topk_pool(probs: torch.Tensor, frac: float = 0.10, kmin: int = 16) -> torch.Tensor:
    """Pool a 1-D vector of per-pixel oil probabilities inside one box.

    k scales with the box so the constraint means the same thing for a
    144 px box and a 248,320 px box.
    """
    n = probs.numel()
    if n == 0:
        raise ValueError("topk_pool called on an empty box")
    k = max(kmin, int(frac * n))
    k = min(k, n)
    return probs.topk(k).values.mean()


@dataclass
class WeakLossOutput:
    total: torch.Tensor
    strong: torch.Tensor
    weak_negative: torch.Tensor
    mil: torch.Tensor
    n_strong: int
    n_weak: int
    n_boxes: int


class NetraV03WeakSupervisionLoss(nn.Module):
    """L_total = w_s * L_strong + w_n * L_weak_negative + w_mil * L_MIL

    * L_strong          : standard pixelwise CE on STRONG_PIXEL samples.
    * L_weak_negative   : pixelwise CE on weak samples, OUTSIDE boxes only
                          (inside boxes is IGNORE_INDEX -- identity unknown).
    * L_MIL             : -log(topk_pool(p_oil inside box)) per box, i.e.
                          "an oil object exists in this box".

    Weak supervision never overwrites strong supervision: the three terms
    are computed on disjoint sample sets / disjoint pixel sets and summed.
    """

    def __init__(
        self,
        w_strong: float = 1.0,
        w_weak_negative: float = 1.0,
        w_mil: float = 1.0,
        topk_frac: float = 0.10,
        topk_min: int = 16,
        mil_eps: float = 1e-6,
    ) -> None:
        super().__init__()
        self.w_strong = w_strong
        self.w_weak_negative = w_weak_negative
        self.w_mil = w_mil
        self.topk_frac = topk_frac
        self.topk_min = topk_min
        self.mil_eps = mil_eps
        self.ce = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)

    def forward(
        self,
        logits: torch.Tensor,          # (B, 2, H, W)
        targets: torch.Tensor,         # (B, H, W) 0/1/IGNORE
        sample_types: list[str],       # len B
        box_masks: torch.Tensor | None = None,  # (B, H, W) bool, box interiors
    ) -> WeakLossOutput:
        device = logits.device
        zero = torch.zeros((), device=device)

        strong_idx = [i for i, t in enumerate(sample_types) if t == STRONG_PIXEL]
        weak_idx = [i for i, t in enumerate(sample_types) if t != STRONG_PIXEL]

        # --- strong pixelwise term -------------------------------------
        if strong_idx:
            st = targets[strong_idx]
            if (st != IGNORE_INDEX).any():
                l_strong = self.ce(logits[strong_idx], st)
            else:
                l_strong = zero
        else:
            l_strong = zero

        # --- weak negative term (outside boxes only) -------------------
        if weak_idx:
            wt = targets[weak_idx]
            if (wt != IGNORE_INDEX).any():
                l_weak_neg = self.ce(logits[weak_idx], wt)
            else:
                # every pixel ignored -> no supervision, contribute nothing
                # (guards the NaN that mean-reduction would otherwise give)
                l_weak_neg = zero
        else:
            l_weak_neg = zero

        # --- MIL existence term ----------------------------------------
        mil_terms: list[torch.Tensor] = []
        n_boxes = 0
        if box_masks is not None:
            probs = F.softmax(logits, dim=1)[:, OIL_CLASS]   # (B, H, W)
            for i in weak_idx:
                m = box_masks[i]
                if m.dtype != torch.bool:
                    m = m.bool()
                if not m.any():
                    continue                      # negative/lookalike tile: no box, no MIL
                p = probs[i][m]
                if p.numel() == 0:
                    continue                      # fails safely
                pooled = topk_pool(p, self.topk_frac, self.topk_min)
                mil_terms.append(-torch.log(pooled.clamp_min(self.mil_eps)))
                n_boxes += 1
        l_mil = torch.stack(mil_terms).mean() if mil_terms else zero

        total = self.w_strong * l_strong + self.w_weak_negative * l_weak_neg + self.w_mil * l_mil
        return WeakLossOutput(
            total=total, strong=l_strong, weak_negative=l_weak_neg, mil=l_mil,
            n_strong=len(strong_idx), n_weak=len(weak_idx), n_boxes=n_boxes,
        )
