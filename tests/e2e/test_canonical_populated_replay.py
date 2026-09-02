"""
VARUNA GRID v2 — STEP 2: Populated Canonical Replay E2E.

Proves that ONE populated replay case can execute through the CANONICAL
`GoldenCaseWorkflow` and produce a complete, populated `OperatorCase` +
intelligence-layer projection, without constructing `RealE2EPipeline` or
`CaseWorkflow` directly from this file.

Fixture selected: CASE-VALID (see docs/product/CANONICAL_REPLAY_COMPLETION_REPORT.md
Phase 2 for the full selection rationale). It is the only one of the six
fixtures in `varuna_domain.replay_fixtures` where every stage reaches
PRODUCED, so it is the only fixture that can legitimately exercise the full
downstream chain (CHHAYA, SMRITI, PRAMAN, mission, alerts) rather than
terminating early at a BLOCKED/UNAVAILABLE/OOD stage — which is the correct,
honest behavior for those other fixtures, not a defect to route around here.

`CaseIntelligenceService.run(case_result.run)` is called on `case_result.run`
— the SAME `PipelineRun` object `GoldenCaseWorkflow.run_replay_case()`
already produced via `varuna_domain.replay_fixtures.build_replay_run()`, not
a second execution. This is a read-only reasoning pass over an
already-canonical result, exactly mirroring how `CaseResult.to_operator_case()`
derives a second view from the same `CaseResult` — it does not construct
`RealE2EPipeline` or `CaseWorkflow`, and it does not re-run anything the
canonical workflow already ran.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from varuna_alerts.channels.mock_sms import MockSmsChannel
from varuna_alerts.service import AlertService
from varuna_domain.golden_case_engine import EngineMode, GoldenCaseWorkflow
from varuna_domain.repositories import (
    InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
)
from varuna_infra.inmemory_store import InMemoryObjectStore
from varuna_integration.intelligence import CaseIntelligenceService
from varuna_missions.repository import InMemoryMissionRepository
from varuna_missions.service import MissionService
from varuna_smriti.memory import SmritiStore

FIXTURE_NAME = "CASE-VALID"


def _make_workflow() -> GoldenCaseWorkflow:
    return GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
        object_store=InMemoryObjectStore(),
        mission_service=MissionService(InMemoryMissionRepository()),
        alert_service=AlertService([MockSmsChannel()]),
    )


def _make_smriti_store(tmp_path: Path) -> SmritiStore:
    return SmritiStore(tmp_path / "memory.jsonl")


@pytest.fixture
def workflow() -> GoldenCaseWorkflow:
    return _make_workflow()


@pytest.fixture
def smriti_store(tmp_path: Path) -> SmritiStore:
    return _make_smriti_store(tmp_path)


# --------------------------------------------------------------------------
# 1. Execution goes through GoldenCaseWorkflow (not RealE2EPipeline/CaseWorkflow)
# --------------------------------------------------------------------------

def test_execution_is_via_golden_case_workflow_only(workflow):
    """Static self-check: this test module must not import the classes it is
    explicitly forbidden from constructing directly. Checked via the actual
    imported names in this module's namespace, not a text search (which
    would false-positive on this very docstring)."""
    this_module = __import__(__name__)
    assert not hasattr(this_module, "RealE2EPipeline")
    assert not hasattr(this_module, "CaseWorkflow")
    assert isinstance(workflow, GoldenCaseWorkflow)


# --------------------------------------------------------------------------
# 2. Replay is deterministic
# --------------------------------------------------------------------------

def test_replay_is_deterministic_across_fresh_workflows():
    """Two entirely separate GoldenCaseWorkflow instances (fresh repos, no
    shared state) running the same fixture under the same case_id must
    produce the same deterministic_run_id — determinism is a property of the
    fixture + config, not of one process's cache."""
    wf1 = _make_workflow()
    wf2 = _make_workflow()
    r1 = wf1.run_replay_case("CASE-VALID-DETERMINISM", FIXTURE_NAME)
    r2 = wf2.run_replay_case("CASE-VALID-DETERMINISM", FIXTURE_NAME)
    assert r1.reproducibility.deterministic_run_id == r2.reproducibility.deterministic_run_id
    assert r1.case.status == r2.case.status


def _strip_volatile(obj):
    """Remove wall-clock timestamps and randomly-generated (not
    content-derived) identifiers before comparing two serialized results for
    determinism. Per this task's own Phase 12 instruction: "Do not require
    wall-clock timestamps to be identical." `replay_fixtures.py` stamps
    `created_at`/`computed_at`/`evaluated_at`/alert `timestamp` with
    `datetime.now()` at fixture-build time (a process artifact, not a
    property of the replay's content), and PRAMAN artifact IDs
    (`golden_case_run-{uuid4}`) are randomly generated per registration, not
    a hash of content — neither is a determinism failure when it differs."""
    volatile_keys = {
        "generated_at", "created_at", "computed_at", "evaluated_at",
        "timestamp", "artifact_ids", "idempotency_key",
    }
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in volatile_keys}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def test_serialized_operator_case_is_stable_across_independent_runs(workflow):
    """Full serialized-result determinism (not just deterministic_run_id):
    two independent GoldenCaseWorkflow instances running the same fixture
    under the same case_id must produce OperatorCase JSON that is identical
    once wall-clock timestamps and randomly-generated artifact IDs are
    stripped -- every actual scientific/evidentiary VALUE (decision states,
    evidence modes, hypothesis content, gate states) must match exactly."""
    wf1 = _make_workflow()
    wf2 = _make_workflow()
    r1 = wf1.run_replay_case("CASE-VALID-SERIALIZED", FIXTURE_NAME)
    r2 = wf2.run_replay_case("CASE-VALID-SERIALIZED", FIXTURE_NAME)
    oc1 = r1.to_operator_case(wf1).model_dump(mode="json")
    oc2 = r2.to_operator_case(wf2).model_dump(mode="json")

    assert _strip_volatile(oc1) == _strip_volatile(oc2)


# --------------------------------------------------------------------------
# 3. Case reaches expected terminal state
# --------------------------------------------------------------------------

def test_case_reaches_complete_terminal_state(workflow):
    result = workflow.run_replay_case("CASE-VALID-TERMINAL", FIXTURE_NAME)
    assert result.case.status.value == "complete"
    assert result.case.error is None


# --------------------------------------------------------------------------
# 4 & 5. OperatorCase is populated; expected evidence sections exist
# --------------------------------------------------------------------------

def test_operator_case_is_populated(workflow):
    result = workflow.run_replay_case("CASE-VALID-POPULATED", FIXTURE_NAME)
    oc = result.to_operator_case(workflow)

    for section_name in ("detection", "origin", "attribution",
                         "validity", "forecast", "decision", "mission", "alerts"):
        section = getattr(oc, section_name)
        assert section.status.value == "produced", (
            f"CASE-VALID section {section_name!r} was expected PRODUCED, "
            f"got {section.status.value!r}"
        )
    assert oc.recommendation.value in ("valid", "degraded")


def test_ais_section_correctly_distinguishes_stage_executed_from_evidence_produced(workflow):
    """The exact distinction Phase 4 of this task requires preserving:
    "stage executed" is NOT equivalent to "stage produced evidence." CASE-VALID's
    ais_ingest STAGE runs successfully (StageStatus.PRODUCED) but returns zero
    tracks (n_returned=0) -- a real, valid scientific outcome (no vessels
    nearby), not an integration failure. The OperatorCase section correctly
    reports NOT_YET_PRODUCED for this, because zero tracks is zero AIS
    evidence, even though the stage itself executed without error."""
    result = workflow.run_replay_case("CASE-VALID-AIS-DISTINCTION", FIXTURE_NAME)

    ais_stage = result.run.stages.get("ais_ingest")
    assert ais_stage is not None
    assert ais_stage.status.value == "produced"       # the STAGE executed
    assert ais_stage.value == []                       # but returned no tracks

    oc = result.to_operator_case(workflow)
    assert oc.ais.status.value == "not_yet_produced"    # so the EVIDENCE section is honest
    assert "No AIS tracks" in oc.ais.reason


# --------------------------------------------------------------------------
# 6. Unavailable sections remain explicitly unavailable (negative control,
#    using a DIFFERENT fixture deliberately, to prove the same code path
#    does not fabricate completeness when the input genuinely lacks it)
# --------------------------------------------------------------------------

def test_unavailable_fixture_stays_explicitly_unavailable(workflow):
    result = workflow.run_replay_case("CASE-UNAVAILABLE-CONTROL", "CASE-UNAVAILABLE")
    oc = result.to_operator_case(workflow)
    non_produced = [name for name in
                    ("detection", "origin", "attribution", "validity", "forecast")
                    if getattr(oc, name).status.value != "produced"]
    assert non_produced, (
        "CASE-UNAVAILABLE should leave at least one section explicitly "
        "not-produced — a fully populated OperatorCase here would mean "
        "something fabricated evidence the fixture does not have."
    )


# --------------------------------------------------------------------------
# 7. EvidenceMode is correct, AND engine_mode is surfaced (ADR-0012 fix)
# --------------------------------------------------------------------------

def test_evidence_mode_and_engine_mode_are_both_surfaced_and_distinct(workflow):
    result = workflow.run_replay_case("CASE-VALID-MODES", FIXTURE_NAME)
    oc = result.to_operator_case(workflow)

    # engine_mode: HOW this run was produced.
    assert oc.system_status.engine_mode == EngineMode.REPLAY

    # evidence_mode (per section): WHAT the evidence claims about itself.
    # CASE-VALID's fixture stamps every section REAL by design (it models
    # what a real, successful case's evidence looks like) — the two facts
    # must coexist and be independently readable, never collapsed into one.
    assert oc.detection.evidence_mode.value == "real"
    assert oc.forecast.evidence_mode.value == "real"

    # The distinction this test exists to prove: engine_mode says REPLAY
    # while evidence_mode says REAL, and BOTH are true and both are visible.
    assert oc.system_status.engine_mode != oc.detection.evidence_mode.value


def test_simulated_fixture_never_claims_real_evidence(workflow):
    """Negative control: CASE-SIMULATED must never report evidence_mode=real
    anywhere, proving the same projection code does not silently upgrade
    SIMULATED to REAL for a different fixture."""
    result = workflow.run_replay_case("CASE-SIMULATED-CONTROL", "CASE-SIMULATED")
    oc = result.to_operator_case(workflow)
    for section_name in ("detection", "origin", "attribution", "forecast"):
        section = getattr(oc, section_name)
        if section.evidence_mode is not None:
            assert section.evidence_mode.value != "real", (
                f"CASE-SIMULATED section {section_name!r} reported evidence_mode=real"
            )


# --------------------------------------------------------------------------
# 8. Provenance is preserved
# --------------------------------------------------------------------------

def test_provenance_is_preserved(workflow):
    result = workflow.run_replay_case("CASE-VALID-PROVENANCE", FIXTURE_NAME)
    oc = result.to_operator_case(workflow)
    assert oc.provenance.case_id == "CASE-VALID-PROVENANCE"
    # `manifest_artifact_id` (a full EvidenceManifest) is NOT populated on the
    # GoldenCaseWorkflow path -- only the single "golden_case_run" summary
    # artifact is registered (see docs/product/CANONICAL_REPLAY_GAPS.md).
    # `artifact_ids` IS populated and is the correct thing to assert here.
    assert oc.provenance.artifact_ids
    assert any("golden_case_run" in a for a in oc.provenance.artifact_ids)
    assert result.reproducibility.engine_mode == EngineMode.REPLAY
    assert result.reproducibility.run_id


# --------------------------------------------------------------------------
# 9. No fake REAL claims appear (cross-check against the intelligence layer)
# --------------------------------------------------------------------------

def test_intelligence_layer_composes_on_the_same_canonical_run(workflow, smriti_store):
    """CaseIntelligenceService.run(result.run) — NOT a second pipeline
    execution, a read-only reasoning pass over the run GoldenCaseWorkflow
    already produced. Proves CHHAYA and SMRITI are reachable from a
    GoldenCaseWorkflow-produced result without constructing anything new."""
    result = workflow.run_replay_case("CASE-VALID-INTEL", FIXTURE_NAME)
    intel = CaseIntelligenceService(smriti=smriti_store).run(result.run)

    assert intel.case_id == "CASE-VALID-INTEL"
    assert intel.hypotheses is not None
    assert intel.hypotheses.envelope.mode.value != "real" or \
        intel.ledger.worst_mode(intel.case_id).value == "real"
    # No evidence item may claim REAL when the ledger's own worst_mode says
    # otherwise elsewhere -- for CASE-VALID (all-REAL fixture) this is
    # consistent; the assertion below is the general fail-closed shape.
    assert intel.trace.terminal_action.value == "proceed_to_decision"


# --------------------------------------------------------------------------
# 10. PRAMAN verification succeeds
# --------------------------------------------------------------------------

def test_praman_artifact_is_registered_and_verifies(workflow):
    result = workflow.run_replay_case("CASE-VALID-PRAMAN", FIXTURE_NAME)
    artifact_id = result.case.metadata.get("golden_case_run_artifact_id")
    assert artifact_id is not None
    artifact = workflow.artifacts.get(artifact_id)
    assert artifact is not None
    assert artifact.content_hash is not None
    assert workflow.praman.verify(artifact_id) is True


def test_praman_verify_fails_closed_for_unknown_artifact(workflow):
    """Negative control: verify() must not report success for a
    non-existent artifact. PramanService.verify() fails closed by returning
    False (documented: "Returns False for an artifact whose payload no
    longer matches... or one whose payload was offloaded"), not by raising —
    the fail-closed contract is the return value, not an exception."""
    assert workflow.praman.verify("does-not-exist-12345") is False


# --------------------------------------------------------------------------
# 11. Repeated execution produces the same deterministic run identity/result
# --------------------------------------------------------------------------

def test_repeated_execution_is_idempotent(workflow):
    r1 = workflow.run_replay_case("CASE-VALID-IDEMPOTENT", FIXTURE_NAME)
    r2 = workflow.run_replay_case("CASE-VALID-IDEMPOTENT", FIXTURE_NAME)

    assert r1.idempotent_replay is False
    assert r2.idempotent_replay is True
    assert r1.reproducibility.deterministic_run_id == r2.reproducibility.deterministic_run_id
    assert r1.reproducibility.run_id == r2.reproducibility.run_id


def test_force_rerun_produces_a_new_run_id(workflow):
    r1 = workflow.run_replay_case("CASE-VALID-FORCE", FIXTURE_NAME)
    r2 = workflow.run_replay_case("CASE-VALID-FORCE", FIXTURE_NAME, force=True)
    assert r2.idempotent_replay is False
    # Same fixture + case_id + config => same deterministic_run_id by
    # definition (it is a content hash, not a call-count), but run_id
    # (wall-clock/random execution-instance identifier) must differ.
    assert r1.reproducibility.deterministic_run_id == r2.reproducibility.deterministic_run_id
    assert r1.reproducibility.run_id != r2.reproducibility.run_id


# --------------------------------------------------------------------------
# 12. Failure semantics remain fail-closed
# --------------------------------------------------------------------------

def test_blocked_fixture_fails_closed_not_open(workflow):
    result = workflow.run_replay_case("CASE-BLOCKED-CONTROL", "CASE-BLOCKED")
    assert result.case.status.value == "blocked"
    assert result.case.error is not None
    oc = result.to_operator_case(workflow)
    assert oc.recommendation.value not in ("valid",)


def test_ood_fixture_never_reaches_a_decision(workflow, smriti_store):
    """Cross-check at the intelligence layer: CASE-OOD (modeled on the real
    MC20 null result) must never reach PROCEED_TO_DECISION."""
    result = workflow.run_replay_case("CASE-OOD-CONTROL", "CASE-OOD")
    intel = CaseIntelligenceService(smriti=smriti_store).run(result.run)
    assert intel.trace.terminal_action.value != "proceed_to_decision"
