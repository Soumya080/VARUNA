# ADR-0013: Case/Intelligence Composition Boundary

**Status:** Accepted
**Date:** 2026-09-02
**Session:** VARUNA GRID v2 Integration Track — STEP 3, Unified Product Case Contract

## Context

STEP 2 proved `GoldenCaseWorkflow` is a usable canonical execution surface,
and that `CaseIntelligenceService` (CHHAYA/SMRITI/uncertainty/decision-trace)
can be run, read-only, over the exact `PipelineRun` a `CaseResult` already
carries — without constructing a second pipeline. What STEP 2 did NOT do is
give the frontend/API one coherent object to consume; a caller who wants
both scientific state and intelligence state had to orchestrate two calls
and merge them by hand (as STEP 2's own test and demo builder did).

This ADR decides how that composition should be structured permanently.

## Decision: composition stays external to `GoldenCaseWorkflow`

**`GoldenCaseWorkflow` does NOT call `CaseIntelligenceService` internally.**
A new, separate composition function
(`varuna_integration.product_case.build_product_case()`) sits ABOVE both:

```
GoldenCaseWorkflow.run_case() / .run_replay_case()
        -> CaseResult
                -> build_product_case(result, workflow)
                        -> CaseResult.to_operator_case(workflow)   [existing, unmodified]
                        -> CaseIntelligenceService.run(result.run) [existing, unmodified]
                        -> OperatorCase, with `.intelligence` populated
```

### Why not internalize it

1. **Failure-mode isolation.** `GoldenCaseWorkflow._finalize()` is what
   decides `CaseStatus`, persists the case, and registers the PRAMAN
   artifact — the operations STEP 1/2 proved must be deterministic and
   fail-closed. `CaseIntelligenceService` runs an 8-iteration agentic loop
   over CHHAYA/SMRITI, which are heavier and, being newer, less
   battle-tested than the ten `RealE2EPipeline` stages. If `GoldenCaseWorkflow`
   called it internally, a bug or slowdown in the reasoning layer would sit
   on the critical path of every case creation — including the live API's
   `POST /v1/cases/{id}/reconstruct` equivalents once (if ever) migrated onto
   `GoldenCaseWorkflow`. Keeping it external means the reasoning layer can
   fail, degrade, or evolve independently without touching
   `CaseStatus`/`ReproducibilityRecord` correctness.
2. **Repository evidence, not preference.** The task instruction was to
   evaluate architecture before deciding, "preferring separation of
   responsibilities unless repository evidence strongly requires otherwise."
   No such evidence was found: nothing in `GoldenCaseWorkflow`,
   `CaseResult`, or any existing test requires intelligence output to exist
   for a case to reach a valid terminal state. `derive_case_status()`,
   idempotency, and PRAMAN registration all already work correctly with zero
   knowledge of CHHAYA/SMRITI/uncertainty — STEP 2 proved this directly.
   Internalizing the call would be adding a new hard dependency where none
   was shown to be needed.
3. **One-directional data flow, mechanically enforced.** `build_product_case()`
   only READS `result` and `result.run`; it constructs a NEW `OperatorCase`
   via `model_copy(update=...)` rather than mutating anything.
   `CaseIntelligenceService` has no reference to `Case`, `CaseRepository`, or
   `GoldenCaseWorkflow` at all — it cannot write back to persisted state even
   if it wanted to. This is what makes "intelligence cannot mutate
   `CaseResult`" a structural fact, not a code-review convention — verified
   directly by `tests/integration/test_product_case_composition.py::test_composition_does_not_mutate_case_result_or_run`.
4. **Idempotency has a real, load-bearing edge case.** A cached
   (`idempotent_replay=True`) `CaseResult` carries a `_ReplayedRunView`, not
   a `PipelineRun` — deliberately, since re-exposing `.stages` on a cache hit
   would look like a second execution. `CaseIntelligenceService.run()`
   requires `.stages`. If `GoldenCaseWorkflow` called intelligence
   internally, this edge case would need to be handled INSIDE the engine
   (either by re-running the pipeline just to feed intelligence — defeating
   idempotency — or by inventing a separate caching story for intelligence
   output). Composing externally lets `build_product_case()` handle this
   with one `hasattr(result.run, "stages")` check and an honest
   `NOT_YET_PRODUCED` + reason, without `GoldenCaseWorkflow` needing to know
   intelligence exists.

### Ownership, restated (matches the task's own framing, confirmed correct)

| Responsibility | Owner |
|---|---|
| Case lifecycle, `CaseStatus` | `GoldenCaseWorkflow` |
| Scientific/operational stages (NETRA, PRATIVARTAN, NYAYA, PRAVAAH, ABHIYAN, missions, alerts) | `GoldenCaseWorkflow` (via `RealE2EPipeline` / replay fixtures) |
| Persistence, PRAMAN, event spine | `GoldenCaseWorkflow` |
| Replay, determinism | `GoldenCaseWorkflow` |
| Evidence Ledger, CHHAYA, SMRITI, uncertainty, `NextBestAction`, decision trace | `CaseIntelligenceService` |
| Merging the two into one product-facing object | `varuna_integration.product_case.build_product_case()` (new, this ADR) |

## The contract change: `OperatorCase.intelligence`

`varuna_contracts.operator_case.IntelligenceSection` (new) is added as an
**additive** field on `OperatorCase`, defaulting to a correct
`NOT_YET_PRODUCED` state. `OPERATOR_CASE_SCHEMA_VERSION` stays `"v1"` — this
is additive in the same sense ADR-0012's `engine_mode` field was: every
existing consumer that never populates `.intelligence` keeps working
unmodified (verified: all 19 pre-existing contract tests pass with zero
changes).

**Why `IntelligenceSection`'s sub-fields reuse existing `varuna_contracts`
types rather than dicts or a new type family:** `UncertaintyAssessment`
(`detection_evidence.py`), `SourceHypothesisEnvelope` (`source_hypothesis.py`),
and `DecisionTrace`/`NextBestAction` (`action.py`) were ALL already defined
inside `varuna_contracts` by the product-build session that created
`CaseIntelligenceService` — confirmed by inspection: `varuna_contracts` has
zero imports from any other `varuna_*` package (a genuine leaf dependency),
and these three types already live inside it. Referencing them from
`IntelligenceSection` adds no new cross-package dependency. `memory_hits`
and `evidence_lineage` stay plain `dict`s because that is what
`CaseIntelligence.memory_hits` and `EvidenceLedger.audit_trail()` already
produce — no `varuna_contracts` type for either ever existed upstream, so
typing them here would be inventing structure the source doesn't have.

## Why this is not a second pipeline

`build_product_case()` contains no scientific computation, no reasoning
logic, and constructs neither `RealE2EPipeline` nor `CaseWorkflow` nor a new
`GoldenCaseWorkflow`. It calls exactly two pre-existing entry points and
merges their return values. `tests/integration/test_product_case_composition.py::test_no_second_pipeline_is_created_by_composition`
proves the scientific sections of the composed `OperatorCase` are
byte-identical to calling `result.to_operator_case(workflow)` directly —
composition strictly adds, never recomputes.

## The live API endpoint

`GET /v1/cases/{case_id}/operator-view` is unchanged in its dependency
wiring — it still resolves `CaseWorkflow` via `get_workflow()`, per the
STEP 1 decision not to migrate `apps/api` in this integration track. Because
`IntelligenceSection` is additive with a correct default, this endpoint
**does** now return the unified representation's shape — every response
includes `intelligence`, honestly reporting `NOT_YET_PRODUCED` with the
reason "CaseIntelligenceService was not composed for this case," because
`CaseWorkflow`-produced cases genuinely have no `PipelineRun` to compose
against. This was not worked around: making the endpoint's `intelligence`
field claim `PRODUCED` would require either migrating the endpoint's DI to
`GoldenCaseWorkflow` (explicitly out of scope for this track, and the same
large, response-schema-affecting change STEP 1 already declined) or
fabricating intelligence output for a case that never ran through the
pipeline it depends on — the latter is exactly what this whole integration
track exists to prevent.

**Verified:** `tests/contract/test_operator_case.py::test_operator_view_endpoint_reports_intelligence_honestly_unavailable`.

## How a future frontend/live-data caller should consume this

```python
result = workflow.run_case(case_id, gold_dir=...)   # or run_replay_case()
product_case = build_product_case(result, workflow, smriti=smriti_store)
# product_case is a normal OperatorCase — every existing field means what it
# always meant, plus `.intelligence` for CHHAYA/SMRITI/uncertainty/decision-trace.
```

No caller needs to know `CaseIntelligenceService`, `EvidenceLedger`, or
`AgenticLoop` exist. If/when `apps/api` migrates its case-mutation endpoints
onto `GoldenCaseWorkflow` (STEP 2's completion report already named this as
the largest open recommendation), the endpoint handler becomes a two-line
change: call `build_product_case()` instead of `result.to_operator_case()`.

## Alternatives considered

- **Internal call from `GoldenCaseWorkflow`** — rejected per the four
  reasons above; revisit only if a real caller needs intelligence to affect
  `CaseStatus` (none does today).
- **A brand-new `UnifiedProductCase` wrapper type**, separate from
  `OperatorCase`, nesting both under sibling keys — rejected: would break
  the two existing tests that read `OperatorCase` fields at the top level
  (`test_operator_view_endpoint_is_read_only_and_additive` reads
  `body["case_id"]` directly), violating "preserve backward compatibility
  where feasible." Extending `OperatorCase` additively achieves the same
  goal with zero breakage.
- **Typing `IntelligenceSection`'s sub-fields as loosely as `dict`
  everywhere** — rejected once it was confirmed the real typed contracts
  already live in the same package; using them costs nothing and preserves
  the type safety `OperatorCase`'s other sections already have.
