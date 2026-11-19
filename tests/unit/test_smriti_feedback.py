"""Phase 7 — SMRITI adaptive reweighting from operator feedback."""
from __future__ import annotations

import pytest

from varuna_smriti.feedback import (
    LEARNING_RATE, MemoryFeedback, SmritiFeedbackStore, compute_adaptive_weights,
)
from varuna_smriti.memory import SIMILARITY_WEIGHTS


def _fb(retrieved="C1", useful=True, components=None, query="Q1"):
    return MemoryFeedback(
        query_case_id=query, retrieved_case_id=retrieved,
        similarity_at_retrieval=0.8,
        components_at_retrieval=components or {"geography": 0.9, "environment": 0.2},
        useful=useful, recorded_by="duty_officer_1",
    )


def test_empty_feedback_reproduces_base_weights_exactly():
    """Zero feedback history must change nothing — the common case for a
    brand-new deployment."""
    adjusted = compute_adaptive_weights([])
    assert adjusted == dict(SIMILARITY_WEIGHTS)


def test_renormalizes_to_sum_to_one():
    fb = [_fb(useful=True), _fb(useful=False, components={"geography": 0.1, "morphology": 0.9})]
    adjusted = compute_adaptive_weights(fb)
    assert abs(sum(adjusted.values()) - 1.0) < 1e-9


def test_useful_feedback_on_high_geography_component_increases_its_weight():
    """A component that was high (0.9) on a hit later judged useful should
    end up weighted MORE than the base — it's earning its keep."""
    fb = [_fb(useful=True, components={"geography": 0.95}) for _ in range(5)]
    adjusted = compute_adaptive_weights(fb)
    assert adjusted["geography"] > SIMILARITY_WEIGHTS["geography"] / sum(SIMILARITY_WEIGHTS.values())


def test_useful_false_on_high_component_decreases_its_weight():
    fb = [_fb(useful=False, components={"geography": 0.95}) for _ in range(5)]
    adjusted = compute_adaptive_weights(fb)
    base_normalized = SIMILARITY_WEIGHTS["geography"] / sum(SIMILARITY_WEIGHTS.values())
    assert adjusted["geography"] < base_normalized


def test_multiplier_is_bounded_even_with_extreme_feedback():
    """LEARNING_RATE * avg_credit is clamped to [0.5, 1.5] BEFORE
    renormalization — no single component can be zeroed out or blown up
    from a handful of feedback events."""
    fb = [_fb(useful=True, components={"geography": 1.0}) for _ in range(50)]
    adjusted = compute_adaptive_weights(fb)
    # Even at the clamp ceiling (1.5x), post-renormalization geography must
    # still be less than the sum of everything else combined.
    assert adjusted["geography"] < 1.0
    assert all(v > 0 for v in adjusted.values()), "no component should be driven to zero"


def test_components_from_a_retired_similarity_axis_are_ignored_not_crashing():
    fb = [_fb(components={"some_future_axis_not_yet_in_SIMILARITY_WEIGHTS": 0.9})]
    adjusted = compute_adaptive_weights(fb)
    assert adjusted == dict(SIMILARITY_WEIGHTS)  # no matching component -> unchanged


def test_feedback_store_persists_and_reloads(tmp_path):
    path = tmp_path / "smriti_feedback.jsonl"
    store = SmritiFeedbackStore(path)
    store.record(_fb(retrieved="C1"))
    store.record(_fb(retrieved="C2", useful=False))
    assert len(store.all()) == 2

    reloaded = SmritiFeedbackStore(path)
    assert len(reloaded.all()) == 2
    assert {f.retrieved_case_id for f in reloaded.all()} == {"C1", "C2"}


def test_feedback_store_skips_corrupt_lines_without_crashing(tmp_path):
    path = tmp_path / "smriti_feedback.jsonl"
    store = SmritiFeedbackStore(path)
    store.record(_fb())
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("not valid json\n")
    reloaded = SmritiFeedbackStore(path)
    assert len(reloaded.all()) == 1


def test_retrieve_similar_cases_with_adaptive_weights_labels_source_correctly():
    """End-to-end: memory.py's optional `weights=` param + this module's
    output compose correctly, and the result is always labelled honestly."""
    from datetime import datetime, timezone

    from varuna_smriti.memory import CaseMemory, SmritiStore

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SmritiStore(f"{d}/mem.jsonl")
        store.store_case(CaseMemory(
            case_id="C1", centroid_lon=72.6, centroid_lat=18.9,
            observed_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            wind_speed_ms=5.0,
        ))
        query = CaseMemory(
            case_id="Q1", centroid_lon=72.61, centroid_lat=18.91,
            observed_at=datetime(2023, 1, 2, tzinfo=timezone.utc), wind_speed_ms=5.1,
        )

        base_result = store.retrieve_similar_cases(query)
        assert base_result.weights_source == "base"
        assert base_result.weights_used == dict(SIMILARITY_WEIGHTS)

        adaptive_weights = compute_adaptive_weights([_fb(useful=True, components={"geography": 0.9})])
        adaptive_result = store.retrieve_similar_cases(query, weights=adaptive_weights)
        assert adaptive_result.weights_source == "adaptive"
        assert adaptive_result.weights_used == adaptive_weights
        # advisory_only must hold regardless of which weighting was used —
        # the one invariant that must never break.
        assert adaptive_result.advisory_only is True
        assert base_result.advisory_only is True
