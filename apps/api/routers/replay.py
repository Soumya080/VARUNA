"""
VARUNA GRID — replay case router (STEP 4, frontend integration track).

Read-only. The ONLY route in `apps/api` that runs cases through
`GoldenCaseWorkflow` (via `dependencies.get_golden_case_workflow()`) and
composes the unified `OperatorCase` via `build_product_case()`
(ADR-0013). Added because Phase 1 of this task confirmed
`GET /v1/cases/{case_id}/operator-view` is still backed by the legacy
`CaseWorkflow`, which produces no `PipelineRun` for the intelligence layer
to compose against — so no existing route could serve a fully-populated
CASE-VALID replay to the frontend.

Why a new route rather than extending `/v1/cases/{case_id}/operator-view`:
that route's `case_id` path segment names an already-created `CaseWorkflow`
case (created via `POST /v1/cases`); a replay fixture has no such case and
no `CaseWorkflow` involvement at all. Reusing the same URL shape for two
different case-creation models would be more confusing than a clearly
separate, additively-named path — see
docs/architecture/ADR-0014-frontend-replay-endpoint.md for the full
reasoning. This is NOT a parallel competing `OperatorCase` schema: the
response model is the SAME `OperatorCase` (with its STEP-3 `intelligence`
field) every other case route already returns.

BUG FOUND AND FIXED (this session's runtime diagnostic, see
docs/product/FRONTEND_RUNTIME_DIAGNOSTIC.md): `GoldenCaseWorkflow.run_replay_case()`
is idempotent per `(case_id, config)` — the SECOND and every subsequent call
with the same `case_id` returns a cached `CaseResult` whose `.run` is a
`_ReplayedRunView`, not a re-runnable `PipelineRun`
(golden_case_engine.py). `build_product_case()` correctly (per its own
documented contract, ADR-0013) reports `.intelligence.status =
NOT_YET_PRODUCED` when it cannot compose against a cached result — but this
route always used the SAME deterministic `case_id`
(`f"REPLAY-{fixture_name}"`), so every request after the first silently lost
CHHAYA/SMRITI/uncertainty/decision-trace data. `force=True` is passed below
to make this READ-ONLY PREVIEW endpoint always recompute — correct here
specifically because a replay fixture is cheap, deterministic, and has no
real idempotency value to preserve (unlike a real scientific run, where
`force=True` would be the wrong default). `deterministic_run_id` still
matches across calls (it is a content hash, not a call-count), so
determinism is not weakened by this — only the intelligence-composability
gap is closed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies import (
    get_alert_orchestrator, get_case_snapshot_store, get_golden_case_workflow,
    get_replay_smriti_store,
)
from varuna_contracts.operator_case import OperatorCase
from varuna_domain.replay_fixtures import FIXTURE_NAMES
from varuna_integration.product_case import build_product_case

router = APIRouter(prefix="/v1/replay", tags=["replay"])

# fixture_name -> fully composed OperatorCase. Bounded by FIXTURE_NAMES (6
# entries), so this cannot grow unbounded. Process-lifetime, like the other
# in-memory singletons in apps.api.dependencies.
_COMPOSED_CACHE: dict[str, OperatorCase] = {}


@router.get("/fixtures")
def list_replay_fixtures() -> dict:
    """The set of valid `fixture_name` values for `GET /v1/replay/{fixture_name}`."""
    return {"fixtures": list(FIXTURE_NAMES)}


@router.get("/{fixture_name}", response_model=OperatorCase)
def get_replay_operator_case(
    fixture_name: str,
    refresh: bool = False,
    workflow=Depends(get_golden_case_workflow),
    smriti=Depends(get_replay_smriti_store),
    orchestrator=Depends(get_alert_orchestrator),
    snapshots=Depends(get_case_snapshot_store),
):
    """Read-only replay preview.

    Composed-response cache (STEP: runtime stabilization, Phase 5): a replay
    fixture is canned, deterministic data, so re-running the whole
    GoldenCaseWorkflow *and* re-running CaseIntelligenceService on every
    single GET was pure recomputation — the dashboard alone triggered it
    twice per page load. We cache the FINISHED OperatorCase, not the
    intermediate PipelineRun: caching the run is what caused the earlier
    idempotency bug, where a cached `_ReplayedRunView` had no `.stages` and
    silently dropped `.intelligence`. Caching the composed product cannot
    hit that failure mode because the intelligence is already inside it.
    `?refresh=true` forces a genuine re-execution.
    """
    if fixture_name not in FIXTURE_NAMES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown replay fixture {fixture_name!r}. Known: {list(FIXTURE_NAMES)}",
        )
    cached = _COMPOSED_CACHE.get(fixture_name)
    if cached is not None and not refresh:
        return cached

    case_id = f"REPLAY-{fixture_name}"
    # force=True: see module docstring. Without this, every request after
    # the first silently lost .intelligence to GoldenCaseWorkflow's
    # idempotency cache.
    result = workflow.run_replay_case(case_id, fixture_name, force=True)
    composed = build_product_case(result, workflow, smriti=smriti)

    # Workstream A: run the operational chain over the composed case.
    # Kept OUTSIDE GoldenCaseWorkflow (ADR-0013 boundary) so an alerting
    # failure can never corrupt a scientific run.
    from varuna_integration.operational_loop import run_operational_loop
    try:
        run_operational_loop(
            composed, snapshots=snapshots, orchestrator=orchestrator,
            event_spine=getattr(workflow, "event_spine", None),
            smriti_store=smriti,
            run_id=getattr(result.run, "run_id", None),
        )
    except Exception:
        # Never fail a read-only case view because alerting had a problem.
        pass

    _COMPOSED_CACHE[fixture_name] = composed
    return composed
