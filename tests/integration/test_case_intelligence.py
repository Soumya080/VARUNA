"""
Case intelligence layer — PipelineRun -> Evidence Ledger -> reasoning.

Uses replay fixtures (no GPU, no real corpus) so the whole chain is exercised
deterministically. The MC20-specific real-data path is covered separately in
tests/integration/test_golden_case_engine_mc20_e2e.py.
"""
from __future__ import annotations

import pytest

from varuna_contracts.action import ActionKind
from varuna_contracts.detection_evidence import OODRisk
from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.source_hypothesis import HypothesisMethod
from varuna_domain.replay_fixtures import build_replay_run
from varuna_evidence import EvidenceKind
from varuna_integration.intelligence import (
    CaseIntelligenceService, assess_ood_from_detection, ledger_from_run,
)
from varuna_smriti.memory import CaseMemory, SmritiStore

pytestmark = pytest.mark.integration


@pytest.fixture
def store(tmp_path) -> SmritiStore:
    s = SmritiStore(tmp_path / "mem.jsonl")
    s.store_case(CaseMemory(case_id="HIST-1", centroid_lon=-89.7, centroid_lat=29.0,
                            top_source_class="natural_seep", outcome="confirmed"))
    return s


# ------------------------------------------------------ ledger projection

def test_only_produced_stages_become_evidence():
    """
    A stage that produced nothing must NOT become an evidence item — recording
    "nothing happened" as evidence would let the item count imply the case is
    better supported than it is.
    """
    run = build_replay_run("CASE-OOD")
    ledger = ledger_from_run(run)
    kinds = {i.kind for i in ledger.for_case(run.case_id)}
    assert EvidenceKind.DETECTION not in kinds     # OOD fixture detects nothing
    for item in ledger.for_case(run.case_id):
        assert item.summary.endswith("produced")


def test_ledger_carries_each_stage_evidence_mode_verbatim():
    run = build_replay_run("CASE-SIMULATED")
    ledger = ledger_from_run(run)
    det = ledger.latest(run.case_id, EvidenceKind.DETECTION)
    assert det is not None
    assert det.mode is EvidenceMode.SIMULATED
    assert ledger.worst_mode(run.case_id) is EvidenceMode.SIMULATED


def test_downstream_evidence_depends_on_forcing():
    run = build_replay_run("CASE-VALID")
    ledger = ledger_from_run(run)
    forcing = ledger.latest(run.case_id, EvidenceKind.FORCING)
    origin = ledger.latest(run.case_id, EvidenceKind.ORIGIN)
    assert forcing is not None and origin is not None
    assert forcing.evidence_id in origin.depends_on
    assert forcing.evidence_id in {i.evidence_id for i in ledger.lineage(origin.evidence_id)}


# ------------------------------------------------------------- OOD assessor

@pytest.mark.parametrize("max_prob,threshold,expected", [
    (0.91, 0.806, OODRisk.IN_DOMAIN),
    (0.50, 0.806, OODRisk.BORDERLINE),
    (3.05e-6, 0.806, OODRisk.OUT_OF_DOMAIN),     # the real MC20 figure
    (None, 0.806, OODRisk.UNKNOWN),
])
def test_ood_heuristic_classifies_activation_levels(max_prob, threshold, expected):
    detail = {"decision_threshold": threshold}
    if max_prob is not None:
        detail["max_probability"] = max_prob
    risk, rationale = assess_ood_from_detection(detail, produced=max_prob is not None)
    assert risk is expected
    assert rationale


def test_ood_rationale_always_declares_itself_a_heuristic():
    """It is not a calibrated OOD score and must never read as one."""
    risk, rationale = assess_ood_from_detection(
        {"max_probability": 3.05e-6, "decision_threshold": 0.806}, produced=False)
    assert risk is OODRisk.OUT_OF_DOMAIN
    assert "HEURISTIC" in rationale


# ------------------------------------------------------- full intelligence

def test_valid_replay_case_gathers_evidence_and_proceeds(store):
    run = build_replay_run("CASE-VALID")
    intel = CaseIntelligenceService(smriti=store).run(run)

    assert intel.trace.terminal_action is ActionKind.PROCEED_TO_DECISION
    kinds = {i.kind for i in intel.ledger.for_case(intel.case_id)}
    assert {EvidenceKind.DATA_QUALITY, EvidenceKind.SOURCE_HYPOTHESIS,
            EvidenceKind.MEMORY} <= kinds
    assert intel.uncertainty.ood_risk is OODRisk.IN_DOMAIN


def test_chhaya_runs_and_is_labelled_as_a_declared_engine(store):
    intel = CaseIntelligenceService(smriti=store).run(build_replay_run("CASE-VALID"))
    assert intel.hypotheses is not None
    assert intel.hypotheses.method is HypothesisMethod.DECLARED_LIKELIHOOD_RATIO
    assert "not a trained or learned model" in intel.hypotheses.methodology_note.lower()


def test_smriti_is_consulted_and_marked_advisory(store):
    intel = CaseIntelligenceService(smriti=store).run(build_replay_run("CASE-VALID"))
    memory = intel.ledger.latest(intel.case_id, EvidenceKind.MEMORY)
    assert memory is not None
    assert memory.observation["advisory_only"] is True
    assert "never override current evidence" in memory.observation["note"]


def test_ood_replay_case_never_reaches_a_decision(store):
    """CASE-OOD is modelled on the real MC20 null. It must fail closed."""
    intel = CaseIntelligenceService(smriti=store).run(build_replay_run("CASE-OOD"))
    assert intel.trace.terminal_action is not ActionKind.PROCEED_TO_DECISION
    assert intel.trace.terminal_action is ActionKind.STOP_INSUFFICIENT_EVIDENCE


def test_unavailable_replay_case_fabricates_nothing(store):
    intel = CaseIntelligenceService(smriti=store).run(build_replay_run("CASE-UNAVAILABLE"))
    assert intel.trace.terminal_action is ActionKind.STOP_INSUFFICIENT_EVIDENCE
    assert intel.detection_evidence is not None
    assert intel.detection_evidence.has_detection is False
    assert intel.detection_evidence.limitations


def test_simulated_case_never_reports_real_evidence_mode(store):
    intel = CaseIntelligenceService(smriti=store).run(build_replay_run("CASE-SIMULATED"))
    assert intel.ledger.worst_mode(intel.case_id) is not EvidenceMode.REAL
    if intel.hypotheses is not None:
        assert intel.hypotheses.envelope.mode is not EvidenceMode.REAL


def test_intelligence_runs_without_a_memory_store():
    """SMRITI is optional; its absence must be reported, not faked."""
    intel = CaseIntelligenceService(smriti=None).run(build_replay_run("CASE-VALID"))
    assert intel.memory_hits == []
    assert intel.ledger.latest(intel.case_id, EvidenceKind.MEMORY) is None


def test_result_serialises_for_praman_and_the_operator_view(store):
    import json
    intel = CaseIntelligenceService(smriti=store).run(build_replay_run("CASE-VALID"))
    payload = intel.to_dict()
    json.dumps(payload, default=str)          # must not raise
    assert payload["audit_trail"]
    assert payload["decision_trace"]
    assert payload["uncertainty"]["dominant_concern"]


def test_data_quality_check_runs_on_the_replay_path(store):
    """M4 fix (docs/product/HONESTY_LEDGER.md #6): the data guard never ran
    at all on the golden/replay path before this — only the legacy
    CaseWorkflow.ingest() path ever evaluated data quality. Every composed
    replay case must now carry a `pipeline_run_data_quality` evidence item."""
    run = build_replay_run("CASE-VALID")
    intel = CaseIntelligenceService(smriti=store).run(run)
    dq_items = [i for i in intel.ledger.for_case(intel.case_id)
                if i.produced_by == "pipeline_run_data_quality"]
    assert len(dq_items) == 1
    assert dq_items[0].observation["verdict"] in ("accepted", "degraded")


def test_data_quality_check_does_not_misfire_on_a_historical_replay_case():
    """The India-Ocean fixtures have a legitimately negative Phi coordinate
    for their historical `obs_time_hours` (see the M3 fix) — the new check
    must judge the REAL `observation_time` instead, or every one of these
    cases would show as degraded by construction, which would be exactly
    the M4 bug this fix exists to avoid re-introducing in a new form."""
    run = build_replay_run("IND-CASE-01")
    intel = CaseIntelligenceService().run(run)
    dq_items = [i for i in intel.ledger.for_case(intel.case_id)
                if i.produced_by == "pipeline_run_data_quality"]
    assert len(dq_items) == 1
    checks = {c["name"]: c["passed"] for c in dq_items[0].observation["checks"]}
    assert checks["observation_time_not_future"] is True, dq_items[0].observation


def test_intelligence_adds_no_science_of_its_own(store):
    """
    Every scientific value must be copied from a stage the canonical pipeline
    ran. The intelligence layer's own additions are limited to evidence
    bookkeeping, OOD assessment, hypotheses and memory.
    """
    run = build_replay_run("CASE-VALID")
    intel = CaseIntelligenceService(smriti=store).run(run)
    produced_by = {i.produced_by for i in intel.ledger.for_case(intel.case_id)}
    allowed_non_pipeline = {
        "data_guard", "ood_assessor", "chhaya", "smriti",
        # M4 fix (docs/product/HONESTY_LEDGER.md #6): the data-quality check
        # newly wired onto the golden/replay path itself.
        "pipeline_run_data_quality",
    }
    for source in produced_by:
        assert source.startswith("pipeline.") or source in allowed_non_pipeline, source
