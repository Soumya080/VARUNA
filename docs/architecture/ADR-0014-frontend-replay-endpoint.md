# ADR-0014: `GET /v1/replay/{fixture_name}` — the frontend's unified-case entry point

**Status:** Accepted
**Date:** 2026-09-02
**Session:** VARUNA GRID v2 Frontend Track — STEP 4

## Context

STEP 4's Phase 1 required verifying whether `GET /v1/cases/{case_id}/operator-view`
already returns the unified `OperatorCase` (with `.intelligence` populated,
per ADR-0013). It does not, and cannot without a larger change: that route
resolves `CaseWorkflow` via `apps/api/dependencies.py::get_workflow()` (STEP 1,
unchanged), and `CaseWorkflow`-produced cases carry no `PipelineRun` for
`CaseIntelligenceService` to compose against — confirmed directly by
`ADR-0013` and STEP 3's own tests. There was, additionally, no existing
route of any kind that ran a case through `GoldenCaseWorkflow` — every
replay fixture (`CASE-VALID` etc.) was only reachable from a script or a
test, never from HTTP.

The frontend's first milestone (Phase 2) requires exactly this: `CASE-VALID`
→ `GoldenCaseWorkflow` → `build_product_case()` → browser, over real HTTP,
with real (not hardcoded) data.

## Decision

Added `apps/api/routers/replay.py`:

- `GET /v1/replay/fixtures` — lists valid fixture names (`FIXTURE_NAMES` from
  `varuna_domain.replay_fixtures`).
- `GET /v1/replay/{fixture_name}` — runs `GoldenCaseWorkflow.run_replay_case(
  f"REPLAY-{fixture_name}", fixture_name)`, then `build_product_case()`,
  returning the SAME `OperatorCase` response model every other case route
  returns (not a new schema).

`apps/api/dependencies.py` gained `get_golden_case_workflow()` (a second,
independent DI provider alongside the existing `get_workflow()` — in-memory
repos, its own singleton, never shared with `CaseWorkflow`'s) and
`get_replay_smriti_store()` (a file-backed `SmritiStore` at
`reports/demo/api_replay_smriti_memory.jsonl`, mirroring STEP 2's demo
builder).

## Why a new route, not extending the existing one

`/v1/cases/{case_id}/operator-view`'s `case_id` names a case created via
`POST /v1/cases`, which only `CaseWorkflow` knows about. A replay fixture
has no such case and no `CaseWorkflow` involvement — retrofitting fixture
semantics onto that URL would mean the SAME path shape means two
structurally different things depending on which `case_id` string happens
to be passed, which is a worse compatibility hazard than an additively
named new path. This also keeps the change reviewable against the STEP-1
canonical-workflow guard: `replay.py` and its DI provider reference
`GoldenCaseWorkflow` exclusively — verified, the guard test passes
unmodified.

**Not a parallel competing contract.** `response_model=OperatorCase` is
literally the same Pydantic class `/operator-view` already returns. A
frontend component written against one works against the other without
modification — the only difference a consumer sees is that this route's
`.intelligence` field is actually `PRODUCED`.

## Consequences

- The live `/operator-view` endpoint is untouched — zero risk to existing
  consumers or tests.
- The frontend has exactly one real, populated, intelligence-complete case
  to build against today: any of the six replay fixtures, reached via
  `/v1/replay/{fixture_name}`.
- When `apps/api`'s case-mutation endpoints eventually migrate to
  `GoldenCaseWorkflow` (STEP 2/3's standing recommendation), this route's
  `GoldenCaseWorkflow` DI provider and its composition call are already the
  pattern to reuse — this ADR's route is not throwaway scaffolding.
- No authentication was added to this route, matching the convention of
  every other read-only (`GET`) case route in this file (`get_case`,
  `get_phi`, `get_attribution`, `get_validity`, `get_operator_view` are all
  unauthenticated today; only state-mutating `POST` routes require a
  `Principal`). If read-endpoint authorization is added repo-wide in a
  future task, this route should be included in that pass, not singled out.
