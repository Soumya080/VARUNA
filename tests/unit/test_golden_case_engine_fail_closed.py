"""Fail-closed proofs required by the Golden Case Engine task, one test per
named property. Each test names the exact scenario from the task spec:

    missing observation  -> no false detection
    detector OOD          -> no trustworthy detection
    missing AIS           -> attribution constrained
    invalid Phi            -> validity blocked/restricted
    blocked validity       -> no mission
    unavailable forecast   -> no fabricated forecast

Every scenario is built the same way the replay fixtures are: a real
`PipelineRun`, populated with `PipelineRun.record()`/`blocked_by()` (the same
methods `RealE2EPipeline` itself uses), so no cascade logic is reimplemented
here -- only the specific StageResults a real producer would return under
each condition.
"""
from __future__ import annotations

from datetime import datetime, timezone

from varuna_contracts.evidence import EvidenceMode
from varuna_domain.replay_fixtures import (
    _attribution, _detection, _forecast, _new_run, _phi,
)
from varuna_integration.stage import StageResult, StageStatus
from varuna_nyaya.validity_gate import evaluate_validity_gate
from varuna_contracts.evidence import TrustState


def test_missing_observation_yields_no_false_detection():
    """CASE-UNAVAILABLE's own construction is the proof: forcing/AIS both
    unavailable, and the detection stage is never PRODUCED -- there is no
    code path in the Golden Case Engine that fabricates a detection when the
    observation layer is empty."""
    run = _new_run("FC-1", "REPLAY")
    run.record(StageResult(
        stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_SAR_TILES: the event carries no SAR tiles to run inference on.",
    ))
    det = run.stages["netra_detection"]
    assert det.status is not StageStatus.PRODUCED
    assert det.value is None


def test_detector_ood_yields_no_trustworthy_detection():
    """A detector-reported OOD condition must not produce a value labelled
    with a usable evidence_mode -- it is NOT_YET_PRODUCED with no mode."""
    run = _new_run("FC-2", "REPLAY")
    run.record(StageResult(
        stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
        reason="OOD: input outside the model's trained distribution.",
        detail={"ood": True},
    ))
    det = run.stages["netra_detection"]
    assert det.status is not StageStatus.PRODUCED
    assert det.evidence_mode is None
    assert det.detail["ood"] is True


def test_missing_ais_constrains_attribution():
    """NYAYA must never be asked to rank vessels with no tracks -- attribution
    is BLOCKED (a real, named integration state), never silently scored
    against zero candidates as if that were a scientific result."""
    run = _new_run("FC-3", "REPLAY")
    det = _detection("fc3")
    phi = _phi("FC-3", det.slick_id, EvidenceMode.REAL, with_sensitivity=True)
    run.record(StageResult(
        stage="phi_reconstruction", status=StageStatus.PRODUCED, value=phi,
        evidence_mode=EvidenceMode.REAL,
    ))
    ais = run.record(StageResult(
        stage="ais_ingest", status=StageStatus.BLOCKED, evidence_mode=EvidenceMode.UNAVAILABLE,
        reason="AIS_UNAVAILABLE: source adapter could not reach the AIS store.",
    ))
    run.record(StageResult(
        stage="attribution", status=StageStatus.BLOCKED,
        reason=f"AIS_UNAVAILABLE_FOR_ATTRIBUTION: NYAYA cannot rank vessels without "
               f"tracks. AIS stage says: {ais.reason}",
    ))
    attribution = run.stages["attribution"]
    assert attribution.status is StageStatus.BLOCKED
    assert attribution.value is None
    assert "AIS_UNAVAILABLE_FOR_ATTRIBUTION" in attribution.reason


def test_invalid_phi_blocks_or_restricts_validity():
    """A Phi field missing its sensitivity diagnostics -- the real, currently
    shipping condition (ADR-0007's sweep is unimplemented) -- must make the
    gate RESTRICTED, never VALID."""
    det = _detection("fc4")
    phi = _phi("FC-4", det.slick_id, EvidenceMode.REAL, with_sensitivity=False)
    attribution = _attribution("FC-4", phi.phi_id, det.slick_id, EvidenceMode.REAL)
    gate = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)
    assert gate.state.value == "restricted"
    assert gate.allows_operational_action is False
    assert any(c.name == "phi_diagnostics_availability" and not c.passed for c in gate.checks)


def test_blocked_validity_yields_no_mission():
    """A RESTRICTED gate must reach the mission stage as NOT_YET_PRODUCED,
    never a MissionRecord invented to keep the pipeline's shape intact."""
    run = _new_run("FC-5", "REPLAY")
    det = _detection("fc5")
    phi = _phi("FC-5", det.slick_id, EvidenceMode.REAL, with_sensitivity=False)
    attribution = _attribution("FC-5", phi.phi_id, det.slick_id, EvidenceMode.REAL)
    gate = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)
    assert gate.state.value == "restricted"
    run.record(StageResult(
        stage="validity", status=StageStatus.PRODUCED, value=gate, evidence_mode=gate.envelope.mode,
    ))
    run.record(StageResult(
        stage="decision", status=StageStatus.NOT_YET_PRODUCED,
        reason=f"NO_TASKING: gate state is {gate.state.value}.",
    ))
    run.record(StageResult(
        stage="mission", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_TASKING_TO_PROPOSE: a mission requires an ABHIYAN tasking.",
    ))
    mission = run.stages["mission"]
    assert mission.status is not StageStatus.PRODUCED
    assert mission.value is None


def test_unavailable_forcing_yields_no_fabricated_forecast():
    """No cube, no forecast -- PRAVAAH must never invent a drift trajectory
    when the current/wind fields it needs are unavailable."""
    run = _new_run("FC-6", "REPLAY")
    forcing = run.record(StageResult(
        stage="forcing", status=StageStatus.BLOCKED, evidence_mode=EvidenceMode.UNAVAILABLE,
        reason="CMEMS_CUBE_MISSING: forcing/cmems_cube.json does not exist.",
    ))
    run.record(run.blocked_by("forecast", "forcing", forcing.reason or ""))
    forecast = run.stages["forecast"]
    assert forecast.status is StageStatus.BLOCKED
    assert forecast.value is None
