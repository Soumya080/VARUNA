"""Phase 4 + 16: mathematical proofs and failure-mode tests for the v0.3
MIL weak-supervision loss. All EXECUTED, deterministic."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages"))

from varuna_netra.training.weak_supervision import (  # noqa: E402
    IGNORE_INDEX,
    NEGATIVE_OR_LOOKALIKE,
    STRONG_PIXEL,
    WEAK_BOX_OIL,
    NetraV03WeakSupervisionLoss,
    topk_pool,
)

H = W = 32


def _logits(oil_logit_map: torch.Tensor) -> torch.Tensor:
    """Build (1,2,H,W) logits with a given OIL-channel logit map."""
    bg = torch.zeros(1, 1, H, W)
    return torch.cat([bg, oil_logit_map.view(1, 1, H, W)], dim=1).requires_grad_(True)


def _box(y0=8, y1=16, x0=8, x1=16):
    m = torch.zeros(1, H, W, dtype=torch.bool)
    m[:, y0:y1, x0:x1] = True
    return m


def _weak_target(box):
    t = torch.zeros(1, H, W, dtype=torch.long)
    t[box] = IGNORE_INDEX
    return t


# ---------------- Phase 4: the eight required proofs ----------------

def test_1_all_low_probability_in_box_gives_high_mil_loss():
    box = _box()
    lg = _logits(torch.full((H, W), -5.0))       # p_oil ~ 0.0067 everywhere
    out = NetraV03WeakSupervisionLoss()(lg, _weak_target(box), [WEAK_BOX_OIL], box)
    assert out.mil.item() > 4.0, f"expected high MIL loss, got {out.mil.item()}"


def test_2_one_strong_region_in_box_decreases_mil_loss():
    box = _box()
    low = torch.full((H, W), -5.0)
    hi = low.clone()
    hi[10:14, 10:14] = 5.0                        # a real object-sized region
    l_low = NetraV03WeakSupervisionLoss()(_logits(low), _weak_target(box), [WEAK_BOX_OIL], box).mil
    l_hi = NetraV03WeakSupervisionLoss()(_logits(hi), _weak_target(box), [WEAK_BOX_OIL], box).mil
    assert l_hi.item() < l_low.item(), "MIL loss must fall when the box contains oil"


def test_3_pixels_outside_box_do_not_affect_the_mil_term():
    box = _box()
    a = torch.full((H, W), -5.0)
    b = a.clone()
    b[0:4, 0:4] = 8.0                             # far outside the box
    mil_a = NetraV03WeakSupervisionLoss()(_logits(a), _weak_target(box), [WEAK_BOX_OIL], box).mil
    mil_b = NetraV03WeakSupervisionLoss()(_logits(b), _weak_target(box), [WEAK_BOX_OIL], box).mil
    assert torch.allclose(mil_a, mil_b, atol=1e-7)


def test_4_mil_produces_positive_learning_gradient_inside_the_box():
    box = _box()
    lg = _logits(torch.full((H, W), -5.0))
    out = NetraV03WeakSupervisionLoss()(lg, _weak_target(box), [WEAK_BOX_OIL], box)
    # backward the MIL TERM ALONE -- out.total also contains the weak-negative
    # CE term, which legitimately supervises pixels outside the box.
    out.mil.backward()
    g_oil = lg.grad[0, 1]
    inside = g_oil[box[0]]
    # negative gradient on the OIL logit => gradient descent RAISES it
    assert (inside < 0).any(), "MIL must push the oil logit UP somewhere inside the box"
    assert torch.count_nonzero(g_oil[~box[0]]) == 0, "the MIL term must not touch pixels outside the box"


def test_5_formulation_does_not_require_knowing_the_true_positive_location():
    """Two boxes whose oil sits in different places must be treated
    identically -- the loss depends only on existence, not location."""
    box = _box()
    a = torch.full((H, W), -5.0); a[9:13, 9:13] = 5.0
    b = torch.full((H, W), -5.0); b[12:16, 12:16] = 5.0
    mil_a = NetraV03WeakSupervisionLoss()(_logits(a), _weak_target(box), [WEAK_BOX_OIL], box).mil
    mil_b = NetraV03WeakSupervisionLoss()(_logits(b), _weak_target(box), [WEAK_BOX_OIL], box).mil
    assert torch.allclose(mil_a, mil_b, atol=1e-6)


def test_6_no_nan_for_valid_boxes_and_gradients_are_finite():
    for fill in (-20.0, -5.0, 0.0, 5.0, 20.0):
        box = _box()
        lg = _logits(torch.full((H, W), fill))
        out = NetraV03WeakSupervisionLoss()(lg, _weak_target(box), [WEAK_BOX_OIL], box)
        assert torch.isfinite(out.total), f"non-finite loss at logit {fill}"
        out.total.backward()
        assert torch.isfinite(lg.grad).all(), f"non-finite grad at logit {fill}"


def test_7_empty_box_fails_safely_not_with_nan():
    empty = torch.zeros(1, H, W, dtype=torch.bool)
    lg = _logits(torch.full((H, W), -5.0))
    t = torch.zeros(1, H, W, dtype=torch.long)
    out = NetraV03WeakSupervisionLoss()(lg, t, [NEGATIVE_OR_LOOKALIKE], empty)
    assert out.n_boxes == 0 and float(out.mil) == 0.0
    assert torch.isfinite(out.total)


def test_8_all_ignored_weak_sample_does_not_produce_nan():
    box = torch.ones(1, H, W, dtype=torch.bool)   # box covers whole tile
    lg = _logits(torch.full((H, W), -5.0))
    out = NetraV03WeakSupervisionLoss()(lg, _weak_target(box), [WEAK_BOX_OIL], box)
    assert torch.isfinite(out.total), "all-ignore weak sample must not NaN"
    out.total.backward()
    assert torch.isfinite(lg.grad).all()


# ---------------- Phase 16: failure modes ----------------

def test_isolated_hot_pixel_cannot_cheaply_satisfy_mil():
    """The decisive anti-exploitation property: one pathological pixel
    must NOT satisfy the constraint the way a real object does."""
    box = _box(0, 32, 0, 32)                       # large box, 1024 px
    noise = torch.full((H, W), -5.0)
    one = noise.clone(); one[0, 0] = 20.0          # single saturated pixel
    obj = noise.clone(); obj[4:12, 4:12] = 5.0     # genuine object (64 px)
    L = NetraV03WeakSupervisionLoss()
    m_noise = L(_logits(noise), _weak_target(box), [WEAK_BOX_OIL], box).mil.item()
    m_one = L(_logits(one), _weak_target(box), [WEAK_BOX_OIL], box).mil.item()
    m_obj = L(_logits(obj), _weak_target(box), [WEAK_BOX_OIL], box).mil.item()
    assert m_obj < m_one, "a real object must satisfy MIL better than one hot pixel"
    assert (m_noise - m_one) < 0.5 * (m_noise - m_obj), (
        "one hot pixel must not capture most of the achievable MIL reduction"
    )


@pytest.mark.parametrize("box", [_box(0, 2, 0, 2), _box(0, 32, 0, 32), _box(30, 32, 30, 32)])
def test_tiny_huge_and_boundary_boxes_are_all_finite(box):
    lg = _logits(torch.full((H, W), -5.0))
    out = NetraV03WeakSupervisionLoss()(lg, _weak_target(box), [WEAK_BOX_OIL], box)
    assert torch.isfinite(out.total)
    out.total.backward()
    assert torch.isfinite(lg.grad).all()


def test_topk_pool_is_stable_across_box_sizes():
    torch.manual_seed(0)
    vals = []
    for n in (144, 3200, 27019):
        p = torch.rand(n) * 0.1
        p[: max(1, int(0.05 * n))] = 0.9
        vals.append(float(topk_pool(p)))
    assert max(vals) - min(vals) < 0.15, f"pooling must not depend strongly on box size: {vals}"


def test_topk_pool_rejects_empty_box():
    with pytest.raises(ValueError):
        topk_pool(torch.empty(0))


def test_strong_and_weak_terms_are_computed_on_disjoint_samples():
    box2 = torch.zeros(2, H, W, dtype=torch.bool)
    box2[1, 8:16, 8:16] = True
    lg = torch.cat([_logits(torch.full((H, W), -5.0)),
                    _logits(torch.full((H, W), -5.0))], dim=0).detach().requires_grad_(True)
    t = torch.zeros(2, H, W, dtype=torch.long)
    t[0, 4:8, 4:8] = 1                # strong sample has real positives
    t[1][box2[1]] = IGNORE_INDEX      # weak sample's box is ignored
    out = NetraV03WeakSupervisionLoss()(lg, t, [STRONG_PIXEL, WEAK_BOX_OIL], box2)
    assert out.n_strong == 1 and out.n_weak == 1 and out.n_boxes == 1
    assert float(out.strong) > 0 and float(out.mil) > 0
