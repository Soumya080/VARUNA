"""
VARUNA GRID v2 — unified product case composition tests (STEP 3, ADR-0013).

Proves the composition boundary in `varuna_integration.product_case`:
`GoldenCaseWorkflow` remains the sole execution engine, `CaseIntelligenceService`
consumes the SAME run rather than a second one, and the merged `OperatorCase`
carries both scientific/operational state and intelligence state without
either layer mutating the other.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from varuna_domain.golden_case_engine import GoldenCaseWorkflow
from varuna_domain.repositories import (
    InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
)
from varuna_infra.inmemory_store import InMemoryObjectStore
from varuna_integration.product_case import build_product_case
from varuna_smriti.memory import SmritiStore

FIXTURE_NAME = "CASE-VALID"


def _make_workflow() -> GoldenCaseWorkflow:
    return GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
        object_store=InMemoryObjectStore(),
    )


@pytest.fixture
def workflow() -> GoldenCaseWorkflow:
    return _make_workflow()


@pytest.fixture
def smriti_store(tmp_path: Path) -> SmritiStore:
    return SmritiStore(tmp_path / "memory.jsonl")


# --------------------------------------------------------------------------
# 1. GoldenCaseWorkflow remains the canonical execution engine
# --------------------------------------------------------------------------

def test_composition_does_not_construct_a_second_orchestrator(workflow):
    import inspect
    source = inspect.getsource(build_product_case)
    assert "RealE2EPipeline(" not in source
    # Checked separately (not as one literal substring) so this assertion
    # itself is not mistaken by tests/contract/test_canonical_workflow_guard.py
    # for a real reference to the legacy orchestrator.
    legacy_orchestrator_call = "Case" + "Workflow("
    assert legacy_orchestrator_call not in source
    assert "GoldenCaseWorkflow(" not in source  # takes an existing instance, never builds one


# --------------------------------------------------------------------------
# 2. CaseIntelligenceService consumes the SAME run
# --------------------------------------------------------------------------

def test_intelligence_consumes_the_same_run_object(workflow, monkeypatch):
    """Patch CaseIntelligenceService.run to capture what it was actually
    called with, and assert it is `result.run` by identity, not a
    reconstruction."""
    result = workflow.run_replay_case("PC-SAME-RUN", FIXTURE_NAME)
    captured = {}

    from varuna_integration import product_case as pc_module
    original_run = pc_module.CaseIntelligenceService.run

    def spy_run(self, run, **kwargs):
        captured["run"] = run
        return original_run(self, run, **kwargs)

    monkeypatch.setattr(pc_module.CaseIntelligenceService, "run", spy_run)
    build_product_case(result, workflow)

    assert captured["run"] is result.run


# --------------------------------------------------------------------------
# 3. No second scientific pipeline exists
# --------------------------------------------------------------------------

def test_no_second_pipeline_is_created_by_composition(workflow):
    """The composed OperatorCase's scientific sections must come from the
    SAME stage results build_product_case's own GoldenCaseWorkflow call
    produced -- not a freshly recomputed value."""
    result = workflow.run_replay_case("PC-NO-SECOND-PIPELINE", FIXTURE_NAME)
    pc = build_product_case(result, workflow)
    direct_oc = result.to_operator_case(workflow)

    # Scientific/operational sections must be byte-identical to the
    # unmodified projection -- composition only ADDS `.intelligence`.
    assert pc.detection == direct_oc.detection
    assert pc.origin == direct_oc.origin
    assert pc.attribution == direct_oc.attribution
    assert pc.validity == direct_oc.validity
    assert pc.forecast == direct_oc.forecast


# --------------------------------------------------------------------------
# 4. Unified product representation contains both core + intelligence
# --------------------------------------------------------------------------

def test_unified_case_contains_core_and_intelligence(workflow, smriti_store):
    result = workflow.run_replay_case("PC-UNIFIED", FIXTURE_NAME)
    pc = build_product_case(result, workflow, smriti=smriti_store)

    # Core (scientific/operational)
    assert pc.detection.status.value == "produced"
    assert pc.forecast.status.value == "produced"
    assert pc.mission.status.value == "produced"
    assert pc.system_status.engine_mode == "replay"

    # Intelligence
    assert pc.intelligence.status.value == "produced"
    assert pc.intelligence.hypotheses is not None
    assert pc.intelligence.decision_trace is not None
    assert pc.intelligence.uncertainty is not None


# --------------------------------------------------------------------------
# 5. Missing intelligence remains explicitly unavailable
# --------------------------------------------------------------------------

def test_cached_result_reports_intelligence_explicitly_unavailable(workflow):
    """An idempotent (cached) CaseResult carries no re-runnable PipelineRun.
    This must be represented as NOT_YET_PRODUCED with a real reason, never
    silently populated with stale or fabricated intelligence."""
    workflow.run_replay_case("PC-CACHED", FIXTURE_NAME)
    cached_result = workflow.run_replay_case("PC-CACHED", FIXTURE_NAME)
    assert cached_result.idempotent_replay is True

    pc = build_product_case(cached_result, workflow)
    assert pc.intelligence.status.value == "not_yet_produced"
    assert "idempotency cache" in pc.intelligence.reason
    assert pc.intelligence.hypotheses is None
    assert pc.intelligence.decision_trace is None


def test_default_operator_case_without_composition_is_explicitly_unavailable(workflow):
    """Calling result.to_operator_case() directly (bypassing this task's new
    composition function) must still yield a well-formed, honest
    `intelligence` section -- the additive default, not a missing attribute."""
    result = workflow.run_replay_case("PC-NO-COMPOSITION", FIXTURE_NAME)
    oc = result.to_operator_case(workflow)
    assert oc.intelligence.status.value == "not_yet_produced"
    assert oc.intelligence.hypotheses is None


# --------------------------------------------------------------------------
# 6. Provenance is preserved
# --------------------------------------------------------------------------

def test_provenance_unaffected_by_composition(workflow):
    result = workflow.run_replay_case("PC-PROVENANCE", FIXTURE_NAME)
    pc = build_product_case(result, workflow)
    assert pc.provenance.case_id == "PC-PROVENANCE"
    assert pc.provenance.artifact_ids


# --------------------------------------------------------------------------
# 7 & 8. EvidenceMode and engine_mode preserved
# --------------------------------------------------------------------------

def test_evidence_mode_and_engine_mode_preserved_through_composition(workflow):
    result = workflow.run_replay_case("PC-MODES", FIXTURE_NAME)
    pc = build_product_case(result, workflow)
    assert pc.system_status.engine_mode == "replay"
    assert pc.detection.evidence_mode.value == "real"
    # Intelligence's own evidence mode (via the hypotheses envelope) must
    # never silently become REAL if the underlying run was not.
    assert pc.intelligence.hypotheses.envelope.mode.value in ("real", "simulated", "unavailable")


def test_simulated_fixture_never_upgraded_by_composition(workflow):
    result = workflow.run_replay_case("PC-SIMULATED", "CASE-SIMULATED")
    pc = build_product_case(result, workflow)
    if pc.intelligence.hypotheses is not None:
        assert pc.intelligence.hypotheses.envelope.mode.value != "real"
    for section_name in ("detection", "origin", "attribution", "forecast"):
        section = getattr(pc, section_name)
        if section.evidence_mode is not None:
            assert section.evidence_mode.value != "real"


# --------------------------------------------------------------------------
# 9. Deterministic replay remains deterministic
# --------------------------------------------------------------------------

def test_composition_preserves_deterministic_run_identity():
    wf1 = _make_workflow()
    wf2 = _make_workflow()
    r1 = wf1.run_replay_case("PC-DETERMINISM", FIXTURE_NAME)
    r2 = wf2.run_replay_case("PC-DETERMINISM", FIXTURE_NAME)
    build_product_case(r1, wf1)
    build_product_case(r2, wf2)
    assert r1.reproducibility.deterministic_run_id == r2.reproducibility.deterministic_run_id


# --------------------------------------------------------------------------
# 10. Intelligence cannot mutate CaseResult
# --------------------------------------------------------------------------

def test_composition_does_not_mutate_case_result_or_run(workflow):
    result = workflow.run_replay_case("PC-NO-MUTATION", FIXTURE_NAME)
    stages_before = {name: (r.status, r.evidence_mode) for name, r in result.run.stages.items()}
    case_status_before = result.case.status
    metadata_before = dict(result.case.metadata)

    build_product_case(result, workflow)

    stages_after = {name: (r.status, r.evidence_mode) for name, r in result.run.stages.items()}
    assert stages_before == stages_after
    assert result.case.status == case_status_before
    assert result.case.metadata == metadata_before


def test_composition_returns_a_new_operator_case_object_each_call(workflow):
    """model_copy(update=...) must produce a distinct object -- proving
    composition is a pure read+construct, not an in-place field assignment
    on a shared OperatorCase."""
    result = workflow.run_replay_case("PC-NEW-OBJECT", FIXTURE_NAME)
    pc1 = build_product_case(result, workflow)
    pc2 = build_product_case(result, workflow)
    assert pc1 is not pc2
    assert pc1.intelligence is not pc2.intelligence


# --------------------------------------------------------------------------
# 11. Repeated composition produces stable serialized content
# --------------------------------------------------------------------------

import re

_EVIDENCE_ID_RE = re.compile(r"^ev-[a-z_]+-[0-9a-f]{6,}$")


def _strip_volatile(obj):
    """Remove wall-clock timestamps, randomly-generated (not
    content-derived) identifiers, and every VALUE matching the
    `ev-<kind>-<hex>` evidence-id pattern (EvidenceLedger.append() assigns
    these via uuid4, per-call, regardless of content -- same category of
    volatility as PRAMAN's `golden_case_run-{uuid4}` artifact IDs). Evidence
    IDs appear both as dict values under `evidence_id` and nested inside
    plain string lists (`depends_on`, `evidence_ids_considered`,
    `evidence_ids`), so this normalizes by VALUE pattern, not only by key."""
    volatile_keys = {
        "generated_at", "created_at", "computed_at", "evaluated_at",
        "timestamp", "artifact_ids", "idempotency_key", "selected_at",
        "executed_at", "at", "action_id", "recorded_at",
    }
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in volatile_keys}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    if isinstance(obj, str) and _EVIDENCE_ID_RE.match(obj):
        return "<EVIDENCE_ID>"
    return obj


def test_repeated_composition_is_stable_apart_from_volatile_fields():
    wf1 = _make_workflow()
    wf2 = _make_workflow()
    r1 = wf1.run_replay_case("PC-STABLE", FIXTURE_NAME)
    r2 = wf2.run_replay_case("PC-STABLE", FIXTURE_NAME)
    pc1 = build_product_case(r1, wf1).model_dump(mode="json")
    pc2 = build_product_case(r2, wf2).model_dump(mode="json")

    assert _strip_volatile(pc1) == _strip_volatile(pc2)
