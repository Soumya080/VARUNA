"""
VARUNA GRID v2 — unified product case composition boundary (ADR-0013, STEP 3).

The single, thin place that combines:

    CaseResult (GoldenCaseWorkflow — scientific/operational state, lifecycle,
                persistence, replay, determinism)
                +
    CaseIntelligence (CaseIntelligenceService — CHHAYA, SMRITI, uncertainty,
                      NextBestAction, decision trace)
                ↓
    ONE OperatorCase, with `.intelligence` populated

This module contains NO scientific logic and NO reasoning logic of its own.
It calls exactly two existing entry points —
`CaseResult.to_operator_case(workflow)` and
`CaseIntelligenceService.run(result.run)` — and merges their outputs. Every
value in the result was computed by one of those two, never by this module.

Why this composition lives here, not inside `GoldenCaseWorkflow`: see
`docs/architecture/ADR-0013-case-intelligence-composition.md`. Short version:
`GoldenCaseWorkflow` owns lifecycle/persistence/determinism and must stay
callable without the reasoning layer's cost or failure modes; the reasoning
layer must never be able to affect `CaseStatus`, `EvidenceMode`, or anything
`GoldenCaseWorkflow` already decided. A composition function that only
READS `CaseResult` and never writes back to it is what keeps that guarantee
mechanically true, not just documented.
"""
from __future__ import annotations

from varuna_contracts.operator_case import IntelligenceSection, OperatorCase, ProducerStatus
from varuna_integration.intelligence import CaseIntelligenceService

# A cached/idempotent replay result's `.run` is a `_ReplayedRunView`
# (packages/varuna_domain/golden_case_engine.py), which deliberately does
# NOT expose `.stages` — it is a stand-in for a cached CaseResult, not a
# re-runnable PipelineRun. CaseIntelligenceService requires `.stages` to do
# anything, so composing intelligence over a cached result is a genuine,
# structural "cannot," not a gap to work around.
_CACHED_RUN_REASON = (
    "This CaseResult was served from GoldenCaseWorkflow's idempotency cache "
    "(idempotent_replay=True); the cached result carries no re-runnable "
    "PipelineRun for the intelligence layer to consume. Call with force=True "
    "or compose intelligence against the original (non-cached) CaseResult."
)


def build_product_case(
    result, workflow, *, smriti=None, chhaya=None, max_iterations: int = 8,
) -> OperatorCase:
    """
    The one canonical composition point. `result` is whatever
    `GoldenCaseWorkflow.run_case()` / `.run_replay_case()` returned;
    `workflow` is the same `GoldenCaseWorkflow` instance that produced it.

    Never mutates `result` or `result.run` — `CaseIntelligenceService.run()`
    only reads stage results off the `PipelineRun` it is given, and this
    function only reads off the `CaseIntelligence` it gets back. There is no
    write path from the intelligence layer back into `CaseResult`,
    `Case`, or any persisted state; the returned `OperatorCase` is a new
    object each call.
    """
    operator_case = result.to_operator_case(workflow)

    if not hasattr(result.run, "stages"):
        intelligence = IntelligenceSection(
            status=ProducerStatus.NOT_YET_PRODUCED, reason=_CACHED_RUN_REASON,
        )
        return operator_case.model_copy(update={"intelligence": intelligence})

    intel = CaseIntelligenceService(
        smriti=smriti, chhaya=chhaya, max_iterations=max_iterations,
    ).run(result.run)

    intelligence = IntelligenceSection(
        status=ProducerStatus.PRODUCED,
        uncertainty=intel.uncertainty,
        hypotheses=intel.hypotheses,
        memory_hits=intel.memory_hits,
        decision_trace=intel.trace,
        next_best_action=(intel.trace.steps[-1].action
                         if intel.trace.steps and intel.trace.steps[-1].action
                         else None),
        evidence_lineage=intel.ledger.audit_trail(intel.case_id),
    )
    return operator_case.model_copy(update={"intelligence": intelligence})
