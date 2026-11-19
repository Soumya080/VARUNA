"""Tests for packages/varuna_domain/replay_fixtures.py -- the six deterministic
CASE-* replay fixtures the Golden Case Engine's REPLAY mode is built on."""
from __future__ import annotations

import json

import pytest

from varuna_domain.golden_case_engine import derive_case_status
from varuna_domain.entities import CaseStatus
from varuna_domain.replay_fixtures import FIXTURE_NAMES, build_replay_run
from varuna_integration.stage import StageStatus


EXPECTED_TERMINAL = {
    "CASE-VALID": CaseStatus.COMPLETE,
    "CASE-RESTRICTED": CaseStatus.COMPLETE,
    "CASE-OOD": CaseStatus.OOD,
    "CASE-UNAVAILABLE": CaseStatus.UNAVAILABLE,
    "CASE-SIMULATED": CaseStatus.COMPLETE,
    "CASE-BLOCKED": CaseStatus.BLOCKED,
}


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_all_six_fixtures_build_without_error(name):
    run = build_replay_run(name)
    assert run.finished_at is not None
    assert len(run.stages) > 0


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_terminal_status_matches_fixture_name(name):
    run = build_replay_run(name)
    status, _reason = derive_case_status(run)
    assert status == EXPECTED_TERMINAL[name], (
        f"{name} expected terminal {EXPECTED_TERMINAL[name].value}, got {status.value}"
    )


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_stage_result_is_json_serializable(name):
    run = build_replay_run(name)
    d = run.to_dict()
    json.dumps(d)  # must not raise


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_no_stage_claims_real_evidence_from_canned_data_incorrectly(name):
    """Fixtures explicitly labelled SIMULATED-source (detection in
    CASE-SIMULATED) must never report evidence_mode=real -- ADR-0006's
    monotonic-worsening rule, checked at the fixture level."""
    run = build_replay_run(name)
    if name == "CASE-SIMULATED":
        det = run.stages.get("netra_detection")
        assert det.evidence_mode.value == "simulated"
        # everything after detection must be simulated-or-worse too
        for stage in ("phi_reconstruction", "attribution", "validity", "forecast"):
            r = run.stages.get(stage)
            if r is not None and r.evidence_mode is not None:
                assert r.evidence_mode.value in ("simulated", "unavailable"), (
                    f"{stage} evidence_mode {r.evidence_mode.value} is not "
                    "worse-than-or-equal to the simulated detection that fed it"
                )


def test_case_valid_gate_actually_says_valid():
    run = build_replay_run("CASE-VALID")
    gate = run.stages["validity"].value
    assert gate.state.value == "valid"
    assert gate.allows_operational_action is True


def test_case_restricted_gate_blocks_on_missing_sensitivity_diagnostics():
    """This is the REAL, currently-shipping gate behaviour (sensitivity sweep
    unimplemented, ADR-0007 TODO(P1)) -- not a fabricated restriction."""
    run = build_replay_run("CASE-RESTRICTED")
    gate = run.stages["validity"].value
    assert gate.state.value == "restricted"
    assert gate.allows_operational_action is False
    names = [c.name for c in gate.checks if not c.passed]
    assert "phi_diagnostics_availability" in names


def test_case_ood_stops_before_reconstruction():
    run = build_replay_run("CASE-OOD")
    det = run.stages["netra_detection"]
    assert det.status is StageStatus.NOT_YET_PRODUCED
    assert det.detail.get("ood") is True
    phi = run.stages["phi_reconstruction"]
    assert phi.status is not StageStatus.PRODUCED


def test_case_unavailable_never_fabricates_a_detection():
    """Missing observation must never produce a false detection -- one of the
    fail-closed properties the master task explicitly requires be proven."""
    run = build_replay_run("CASE-UNAVAILABLE")
    det = run.stages["netra_detection"]
    assert det.status is not StageStatus.PRODUCED
    assert det.value is None


def test_case_blocked_is_a_scoped_break_not_a_blanket_one():
    """PRAVAAH does not depend on PRATIVARTAN -- a PRATIVARTAN failure must
    not block a forecast that had everything it needed."""
    run = build_replay_run("CASE-BLOCKED")
    assert run.stages["phi_reconstruction"].status is StageStatus.BLOCKED
    assert run.stages["forecast"].status is StageStatus.PRODUCED


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_deterministic_modulo_run_id_and_timestamps(name):
    """Two builds of the same fixture must be byte-identical except run_id
    and wall-clock timestamps -- REPLAY must be reproducible."""
    a = build_replay_run(name).to_dict()
    b = build_replay_run(name).to_dict()
    for d in (a, b):
        for key in ("run_id", "started_at", "finished_at", "total_seconds"):
            d.pop(key, None)
        for stage in d["stages"].values():
            stage.pop("runtime_seconds", None)
    assert a == b


def test_unknown_fixture_name_raises():
    with pytest.raises(ValueError, match="unknown replay fixture"):
        build_replay_run("CASE-DOES-NOT-EXIST")
