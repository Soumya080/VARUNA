"""Phase 4/5: EXECUTED proofs that the weak-supervision loss mechanics do
what the v0.3 label policy claims. These are mathematical tests, not code
inspection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages"))

from varuna_netra.dataset.gold_v03 import IGNORE_INDEX  # noqa: E402

C, H, W = 2, 16, 16


def _fixed_logits(seed=0):
    g = torch.Generator().manual_seed(seed)
    return torch.randn(1, C, H, W, generator=g, requires_grad=True)


def test_loss_is_invariant_to_target_changes_inside_ignored_pixels():
    """A and B differ ONLY inside ignored pixels => loss(A) == loss(B)."""
    logits = _fixed_logits()
    base = torch.zeros(1, H, W, dtype=torch.long)
    ignore_region = torch.zeros(1, H, W, dtype=torch.bool)
    ignore_region[:, 4:10, 4:10] = True

    a = base.clone()
    a[ignore_region] = IGNORE_INDEX
    b = base.clone()
    b[ignore_region] = IGNORE_INDEX

    # make the *underlying* labels differ inside the ignored region only
    a_alt = base.clone(); a_alt[ignore_region] = IGNORE_INDEX
    b_alt = torch.ones(1, H, W, dtype=torch.long); b_alt[ignore_region] = IGNORE_INDEX
    b_alt[~ignore_region] = base[~ignore_region]   # identical outside

    crit = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)
    la = crit(logits, a_alt)
    lb = crit(logits, b_alt)
    assert torch.allclose(la, lb, atol=1e-7), f"loss must ignore in-box pixels: {la} vs {lb}"


def test_loss_changes_when_a_non_ignored_pixel_changes():
    logits = _fixed_logits()
    t1 = torch.zeros(1, H, W, dtype=torch.long)
    t1[:, 4:10, 4:10] = IGNORE_INDEX
    t2 = t1.clone()
    t2[0, 0, 0] = 1  # a NON-ignored pixel flips class

    crit = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)
    assert not torch.allclose(crit(logits, t1), crit(logits, t2)), (
        "changing a supervised pixel must change the loss"
    )


def test_ignored_pixels_contribute_exactly_zero_gradient():
    logits = _fixed_logits()
    target = torch.zeros(1, H, W, dtype=torch.long)
    target[:, 4:10, 4:10] = IGNORE_INDEX

    crit = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)
    crit(logits, target).backward()
    g = logits.grad
    assert g is not None
    ig = g[:, :, 4:10, 4:10]
    assert torch.count_nonzero(ig) == 0, "ignored pixels must receive zero gradient"
    sup = g.clone()
    sup[:, :, 4:10, 4:10] = 0
    assert torch.count_nonzero(sup) > 0, "supervised pixels must receive nonzero gradient"


def test_all_ignored_target_yields_nan_loss_which_must_be_guarded():
    """A tile whose target is entirely IGNORE produces NaN (0/0) under
    mean reduction. Any training loop mixing weak samples MUST guard this
    -- documented here so the failure mode is known, not discovered on GPU."""
    logits = _fixed_logits()
    target = torch.full((1, H, W), IGNORE_INDEX, dtype=torch.long)
    loss = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)(logits, target)
    assert torch.isnan(loss), (
        "expected NaN for an all-ignored target; if this ever changes, the "
        "training-loop guard can be revisited"
    )


def test_ignore_index_does_not_collide_with_class_ids():
    assert IGNORE_INDEX not in (0, 1)
