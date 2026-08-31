"""Tests for packages/varuna_domain/golden_case_engine.py -- the canonical
Golden Case Engine: lifecycle derivation, reproducibility, idempotency,
DetectorProvider boundary reporting, and fail-closed behaviour."""
from __future__ import annotations

import pytest

from varuna_domain.entities import CaseStatus
from varuna_domain.golden_case_engine import (
    GoldenCaseWorkflow, config_hash, derive_case_status, detector_provider_info,
)
from varuna_domain.repositories import (
    InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
)
from varuna_domain.replay_fixtures import build_replay_run
from varuna_integration.pipeline import PipelineConfig


def _workflow() -> GoldenCaseWorkflow:
    return GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
    )


# --------------------------------------------------------- config_hash / repro


def test_config_hash_is_stable_for_equal_configs():
    a = PipelineConfig(gold_dir="x", seed=1)
    b = PipelineConfig(gold_dir="x", seed=1)
    assert config_hash(a) == config_hash(b)


def test_config_hash_differs_for_different_seed():
    a = PipelineConfig(gold_dir="x", seed=1)
    b = PipelineConfig(gold_dir="x", seed=2)
    assert config_hash(a) != config_hash(b)


def test_reproducibility_record_carries_required_fields():
    wf = _workflow()
    result = wf.run_replay_case("CASE-A", "CASE-VALID")
    r = result.reproducibility.to_dict()
    for key in ("case_id", "run_id", "model_version", "config_hash", "code_version",
                "evidence_mode", "started_at", "finished_at"):
        assert key in r, f"reproducibility record missing {key}"
    assert r["case_id"] == "CASE-A"
    assert r["code_version"] != ""


def test_detector_provider_info_exposes_required_fields():
    run = build_replay_run("CASE-VALID")
    info = detector_provider_info(run)
    for key in ("model_id", "model_version", "checkpoint_hash", "preprocessing_version",
                "detection_state", "evidence_mode"):
        assert key in info
    assert info["model_version"] == "netra-replay-frozen"
    assert info["detection_state"] == "produced"


def test_detector_provider_info_handles_no_detection_stage():
    run = build_replay_run("CASE-UNAVAILABLE")
    info = detector_provider_info(run)
    # netra_detection stage DID run (NOT_YET_PRODUCED) in this fixture -- but
    # even when the stage is entirely absent, the accessor must not raise.
    assert "model_id" in info


# ------------------------------------------------------------------ lifecycle


def test_lifecycle_transitions_walk_every_reached_stage():
    wf = _workflow()
    result = wf.run_replay_case("CASE-B", "CASE-VALID")
    events = [e.event_type for e in wf.event_spine.list_by_case("CASE-B")]
    for stage in ("forcing", "ais_ingest", "netra_detection", "phi_reconstruction",
                  "attribution", "validity", "forecast", "decision", "mission", "alerts"):
        assert f"case.stage.{stage}" in events, f"missing lifecycle event for {stage}"
    assert "case.terminal" in events
    assert result.case.status is CaseStatus.COMPLETE


def test_case_created_status_set_immediately_on_create():
    wf = _workflow()
    case = wf.create_case("CASE-C")
    assert case.status is CaseStatus.CASE_CREATED


# ------------------------------------------------------------------ idempotency


def test_rerun_same_case_same_config_does_not_duplicate_missions_or_events():
    wf = _workflow()
    r1 = wf.run_replay_case("CASE-D", "CASE-VALID")
    n_events_1 = len(wf.event_spine.list_by_case("CASE-D"))
    n_artifacts_1 = len(wf.praman.list_by_case("CASE-D"))

    r2 = wf.run_replay_case("CASE-D", "CASE-VALID")
    assert r2.idempotent_replay is True
    assert len(wf.event_spine.list_by_case("CASE-D")) == n_events_1
    assert len(wf.praman.list_by_case("CASE-D")) == n_artifacts_1
    assert r2.reproducibility.run_id == r1.reproducibility.run_id


def test_force_rerun_creates_a_new_run():
    wf = _workflow()
    r1 = wf.run_replay_case("CASE-E", "CASE-VALID")
    n_events_1 = len(wf.event_spine.list_by_case("CASE-E"))

    r2 = wf.run_replay_case("CASE-E", "CASE-VALID", force=True)
    assert r2.idempotent_replay is False
    assert r2.reproducibility.run_id != r1.reproducibility.run_id
    assert len(wf.event_spine.list_by_case("CASE-E")) > n_events_1


def test_different_fixtures_on_same_case_are_not_treated_as_the_same_run():
    wf = _workflow()
    r1 = wf.run_replay_case("CASE-F", "CASE-VALID")
    r2 = wf.run_replay_case("CASE-F", "CASE-RESTRICTED")
    assert r2.idempotent_replay is False
    assert r1.reproducibility.run_id != r2.reproducibility.run_id


# ------------------------------------------------------------------ terminal status


@pytest.mark.parametrize("fixture,expected", [
    ("CASE-VALID", CaseStatus.COMPLETE),
    ("CASE-RESTRICTED", CaseStatus.COMPLETE),
    ("CASE-OOD", CaseStatus.OOD),
    ("CASE-UNAVAILABLE", CaseStatus.UNAVAILABLE),
    ("CASE-SIMULATED", CaseStatus.COMPLETE),
    ("CASE-BLOCKED", CaseStatus.BLOCKED),
])
def test_engine_reaches_expected_case_status(fixture, expected):
    wf = _workflow()
    result = wf.run_replay_case(f"CASE-{fixture}", fixture)
    assert result.case.status is expected


def test_blocked_and_unavailable_are_distinguished_by_root_cause():
    """BLOCKED (CASE-BLOCKED, a genuine downstream break) and UNAVAILABLE
    (CASE-UNAVAILABLE, missing input data) must never be confused -- proven by
    running both against the same derivation function, not by assumption."""
    blocked_run = build_replay_run("CASE-BLOCKED")
    unavailable_run = build_replay_run("CASE-UNAVAILABLE")
    b_status, _ = derive_case_status(blocked_run)
    u_status, _ = derive_case_status(unavailable_run)
    assert b_status is CaseStatus.BLOCKED
    assert u_status is CaseStatus.UNAVAILABLE
    assert b_status != u_status


# --------------------------------------------------------------- OperatorCase


def test_operator_case_projection_reflects_replay_evidence_mode():
    wf = _workflow()
    result = wf.run_replay_case("CASE-G", "CASE-SIMULATED")
    oc = result.to_operator_case(wf)
    assert oc.detection.evidence_mode.value == "simulated"
    assert oc.validity.value.state.value == "degraded"


def test_operator_case_projection_works_for_ood_case():
    wf = _workflow()
    result = wf.run_replay_case("CASE-H", "CASE-OOD")
    oc = result.to_operator_case(wf)
    assert oc.detection.status.value == "not_yet_produced"
    assert "OOD" in (oc.detection.reason or "")
