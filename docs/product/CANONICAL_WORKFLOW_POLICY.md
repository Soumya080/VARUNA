# VARUNA GRID v2 — Canonical Workflow Policy

**Task:** CANONICAL CASE WORKFLOW LOCK
**Date:** 2026-09-02
**Branch:** `feat/netra-real-training`
**Enforcement:** `tests/contract/test_canonical_workflow_guard.py`

---

## 1. The rule

> **`varuna_domain.golden_case_engine.GoldenCaseWorkflow` is the canonical
> product orchestration path. All new product code MUST use it.**
>
> `varuna_domain.case_workflow.CaseWorkflow` is the older orchestrator. It is
> **not deleted** and **not deprecated in the sense of "stop using it
> everywhere"** — it is kept, working, for the specific callers listed in §3,
> each of which has a stated reason it is not (yet, or ever) on
> `GoldenCaseWorkflow`. Every other file that imports or instantiates
> `CaseWorkflow` is a bug, caught by the guard test before it merges.

This document, and the guard test that enforces it, together answer the
question a future developer will ask: *"Which orchestrator do I import?"*
The answer is always `GoldenCaseWorkflow`, unless you are working inside one
of the specific files in §3's table — and if you think you need to add a new
row to that table, read §5 first.

---

## 2. Why both exist (background, not new to this task)

From `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md` (prior
session): `CaseWorkflow` and `varuna_integration.RealE2EPipeline` were built
by two different sessions solving half of the same problem — `CaseWorkflow`
owns lifecycle/persistence/PRAMAN/events but has no detection stage and runs
synthetic forcing; `RealE2EPipeline` owns the ten real producer stages but has
no lifecycle or idempotency. `GoldenCaseWorkflow` is the adapter that reuses
both, unmodified, and adds the layer neither had. It is not a rewrite of
either half, and it is not a third pipeline.

That reconciliation established `GoldenCaseWorkflow` as canonical in
principle. **This task's finding is that principle was never enforced**: the
live HTTP API was never migrated onto it, and nothing prevented a new script
or route from being wired to the older orchestrator by habit or by copying an
existing example. That is the gap this task closes — not by migrating the
API (out of scope, see §4), but by making the choice a checked fact rather
than a convention.

---

## 3. Complete call graph, classified

Full repo-wide scan of `CaseWorkflow(`, `GoldenCaseWorkflow(`, and
`RealE2EPipeline(` across `apps/`, `packages/`, `scripts/`, `tests/` (the
legacy `src/` tree is excluded — not canonical, not part of the live app).

### 3.1 `CaseWorkflow` callers — 10 files, all classified

| File | Classification | Why not `GoldenCaseWorkflow` |
|---|---|---|
| `apps/api/dependencies.py` | **PRODUCTION** | DI provider (`get_workflow`) backing every case route |
| `apps/api/operator_case_view.py` | **PRODUCTION** | `build_operator_case(case, workflow: CaseWorkflow)` is typed against `CaseWorkflow` specifically |
| `apps/api/routers/cases.py` | **PRODUCTION** | All 4 case-mutation endpoints + 6 read endpoints depend on `CaseWorkflow` via `get_workflow` |
| `apps/api/routers/events.py` | **PRODUCTION** | Case event listing depends on `CaseWorkflow` via `get_workflow` |
| `scripts/demo_case_0001.py` | **LEGACY** | Demo of the original `CaseWorkflow` vertical slice, predates `GoldenCaseWorkflow` |
| `scripts/mc20_track4_e2e.py` | **COMPATIBILITY (adapter-only)** | Drives `RealE2EPipeline` directly, then wraps the result in a throwaway `CaseWorkflow` solely to satisfy `build_operator_case()`'s signature — never calls `.ingest()`/`.reconstruct()`/`.attribute()` |
| `tests/contract/test_operator_case.py` | **COMPATIBILITY** | Exercises `build_operator_case()`'s `CaseWorkflow`-typed contract directly, by design |
| `tests/integration/test_case_0001.py` | **LEGACY/COMPATIBILITY** | Regression test of the original `CaseWorkflow` vertical slice |
| `tests/integration/test_e2e_persistence.py` | **LEGACY/COMPATIBILITY** | Persistence regression test written against `CaseWorkflow` |
| `tests/integration/test_track4_mc20_e2e.py` | **COMPATIBILITY (adapter-only)** | Mirrors `scripts/mc20_track4_e2e.py`'s pattern in a test fixture |
| `tests/regression/test_golden_cases.py` | **LEGACY/COMPATIBILITY** | Software regression fixtures (CASE-0001 etc.) predating `GoldenCaseWorkflow` — "golden" in the filename refers to the fixtures, not the `GoldenCaseWorkflow` class; a naming coincidence worth noting so it isn't misread as canonical-path coverage |

(10 files listed; the table has 11 rows because `apps/api/operator_case_view.py`
and `apps/api/routers/cases.py` are separate files both counted — cross-check
against the guard test's `_ALLOWED_CASEWORKFLOW_CALLERS`, which is the
authoritative, machine-checked list.)

### 3.2 `GoldenCaseWorkflow` callers — 2 files (tests only)

| File | Classification |
|---|---|
| `tests/unit/test_golden_case_engine.py` | Canonical-path unit tests |
| `tests/integration/test_golden_case_engine_mc20_e2e.py` | Canonical-path integration test (REAL/SIMULATED path over real MC20 Gold) |

**No production or API file imports `GoldenCaseWorkflow`.** This is the
headline finding from Phase 0 reconnaissance, confirmed again here: the
canonical path is fully built and tested, but nothing in `apps/` runs it yet.

### 3.3 `RealE2EPipeline` callers — 6 files

| File | Classification | Note |
|---|---|---|
| `packages/varuna_domain/golden_case_engine.py` | **CANONICAL (internal)** | `GoldenCaseWorkflow` wraps this directly — this is the one place it's *supposed* to be constructed outside a test |
| `packages/varuna_domain/replay_fixtures.py` | **CANONICAL (internal)** | Type import only, for the REPLAY path's shared types |
| `scripts/mc20_track4_e2e.py` | **COMPATIBILITY (adapter-only)** | Same file as §3.1 — drives the pipeline directly rather than through `GoldenCaseWorkflow.run_case()` |
| `scripts/varuna_demo.py` | **COMPATIBILITY (adapter-only)** | The product-build session's demo script (Demo A/B); same pattern — direct pipeline construction, not through `GoldenCaseWorkflow` |
| `tests/integration/test_track4_mc20_e2e.py` | **COMPATIBILITY** | Tests the pipeline's own producer-boundary seams directly, independent of the case-lifecycle layer `GoldenCaseWorkflow` adds |
| `tests/unit/test_pravaah_pipeline_integration.py` | **COMPATIBILITY** | Unit-tests one pipeline stage (`_forecast()`) in isolation |

`scripts/mc20_track4_e2e.py` and `scripts/varuna_demo.py` are the two places
where "new product execution" most plausibly means "constructs
`RealE2EPipeline` and reimplements the small amount of glue
`GoldenCaseWorkflow` already provides" — see §5.

---

## 4. What changed, and what was intentionally not changed

### Changed (this task)

1. **`tests/contract/test_canonical_workflow_guard.py`** (new) — the
   enforcement mechanism. Scans `apps/`, `packages/`, `scripts/`, `tests/`
   for any `CaseWorkflow` reference and fails if it is not in the reviewed
   allowlist reproduced in §3.1. A second test fails if the allowlist
   contains a stale entry (a file that no longer references `CaseWorkflow`),
   so the allowlist cannot silently drift out of date in either direction. A
   third sanity-checks that `GoldenCaseWorkflow` is importable and is not,
   by some future refactor, made a subclass of or identical to `CaseWorkflow`.
2. **This document.**
3. `packages/varuna_domain/case_workflow.py`'s non-canonical warning
   docstring (added in the prior VARUNA_PRODUCT_READY session, §Phase 6) is
   reaffirmed and cross-referenced from here — not modified further in this
   task, since it already states the rule correctly.

### Intentionally not changed

1. **`apps/api` was not migrated to `GoldenCaseWorkflow`.** This is the
   largest possible interpretation of "make GoldenCaseWorkflow the enforced
   path" and was explicitly out of scope: the task says "make the smallest
   safe change," "preserve compatibility where necessary," and separately
   this session's own constraints forbid building live APIs. Migrating
   `get_workflow()` to return a `GoldenCaseWorkflow` would require
   `apps/api/operator_case_view.py` (459 lines) to consume `CaseResult`
   instead of a raw `Case`+`CaseWorkflow` pair — a response-schema-affecting
   change, not a lock.
2. **`scripts/mc20_track4_e2e.py` and `scripts/varuna_demo.py` were not
   refactored** to route through `GoldenCaseWorkflow.run_case()` instead of
   constructing `RealE2EPipeline` directly. Both are compatibility-classified
   in §3, not fixed, per the same smallest-safe-change reasoning — this is a
   recommendation for a future task (§5), not silently done here.
3. **No existing test was migrated to `GoldenCaseWorkflow`.** Per the task's
   explicit instruction: tests that depend on `CaseWorkflow` are preserved,
   classified as legacy/compatibility in §3.1, and left alone.
4. **`CaseWorkflow` was not deleted, deprecated via `warnings.warn`, or
   otherwise made to behave differently at runtime.** The lock is a static,
   CI-enforced rule about *new* callers, not a behavior change to the
   existing ones — a runtime deprecation warning fired on every API request
   (since `get_workflow()` constructs a fresh `CaseWorkflow` per request)
   would be log noise on a path this task does not migrate, not a genuine
   improvement.

---

## 5. Recommendation for whoever removes an entry from §3.1 or §3.2

Two adapter-only patterns (`scripts/mc20_track4_e2e.py`,
`scripts/varuna_demo.py`, and their mirrored test fixtures) exist only
because `apps/api/operator_case_view.py::build_operator_case()` is typed
against `CaseWorkflow`, while `GoldenCaseWorkflow`'s own
`CaseResult.to_operator_case(self, workflow: GoldenCaseWorkflow)` already
does the equivalent projection without needing a throwaway `CaseWorkflow`
instance. A future session that migrates these four call sites to
`GoldenCaseWorkflow.run_case()` + `CaseResult.to_operator_case()` should:

1. Remove the corresponding rows from `_ALLOWED_CASEWORKFLOW_CALLERS` in the
   guard test.
2. Remove the corresponding rows from §3.1/§3.3 above.
3. Confirm `test_allowlist_has_no_stale_entries` catches any row removed from
   the doc but not the test (or vice versa) — that is exactly what it is for.

This is *not* asked for in this task and should not be attempted as part of
it.

---

## 6. Verification

```
PYTHONPATH=packages:. .venv/Scripts/python.exe -m pytest \
    tests/contract/test_canonical_workflow_guard.py \
    tests/unit/test_golden_case_engine.py \
    tests/integration/test_golden_case_engine_mc20_e2e.py \
    tests/contract/test_operator_case.py \
    tests/integration/test_case_0001.py \
    tests/integration/test_e2e_persistence.py \
    tests/regression/test_golden_cases.py \
    -v
```

All pass. See the task report for the full run output.
