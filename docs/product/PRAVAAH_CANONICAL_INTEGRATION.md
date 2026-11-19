# VARUNA GRID v2 — PRAVAAH Canonical Integration

**Task:** Integration Track STEP 5
**Date:** 2026-09-02

## Final status: **PRAVAAH_CANONICAL_VERIFIED**

---

## 1. Previous behavior (Phase 1 diagnosis)

Traced the complete call graph before making any change:

- `RealE2EPipeline._forecast()` (`packages/varuna_integration/pipeline.py`)
  **already** called the real `CubeBackedPravaahProvider.forecast_drift()`
  against real forcing — verified pre-existing, not built this task
  (`tests/unit/test_pravaah_pipeline_integration.py`, unmodified).
- `GoldenCaseWorkflow.run_case()` **already** exercised this end-to-end with
  a `SimulatedSlickProvider` detection against real MC20 CMEMS/ERA5 forcing
  — verified pre-existing
  (`tests/integration/test_golden_case_engine_mc20_e2e.py::test_pravaah_forecast_runs_on_real_mc20_forcing_via_the_canonical_pipeline`,
  unmodified).
- `CASE-VALID` (the replay fixture the frontend actually loads) carries a
  **hand-built** `ForwardForecast` (`replay_fixtures.py::_forecast()`) — by
  design, since replay fixtures are canned data, not live computation.

## 2. Actual root cause (the real gap, not assumed)

`build_product_case()` — STEP 3's composition boundary, the ONLY path a
unified `OperatorCase` is assembled through — had **never once** been
exercised against a `CaseResult` carrying a genuinely-computed (non-fixture)
PRAVAAH forecast. Every existing `build_product_case()` test used
`CASE-VALID`'s hand-built fixture value. This meant "PRAVAAH is load-bearing
in the canonical product flow" was true at the `RealE2EPipeline`/
`GoldenCaseWorkflow` layer but **unverified** at the exact layer the
frontend and PRAMAN actually consume.

Secondary finding: no test proved `build_product_case()` does not
re-invoke PRAVAAH (a literal "second pipeline" risk this task's Phase 3
explicitly forbids) — confirmed correct by construction (the composition
function only reads `result.run.stages["forecast"]`, already computed), but
this had never been asserted, only assumed.

## 3. Files changed

| File | Change |
|---|---|
| `tests/integration/test_pravaah_canonical_product_case.py` (new) | 9 tests proving PRAVAAH is genuinely invoked by `GoldenCaseWorkflow`, its output survives `build_product_case()` unmodified, is never duplicated, fails closed on missing input, and stays correctly labeled SIMULATED when the detection is simulated |
| `frontend/VARUNA-frontend_yash/lib/operator-case-types.ts` | `ForwardForecastValue` properly typed (was a loose `{forecast_id: string; [key: string]: unknown}`); added `LandfallPrediction` |
| `frontend/VARUNA-frontend_yash/components/intelligence-panels.tsx` | New `ForecastPanel` — the frontend gap Phase 6 asked to verify: no dedicated forecast display existed before this task (only a one-line status row inside the pipeline timeline) |
| `frontend/VARUNA-frontend_yash/components/case-intelligence.tsx` | Wired `ForecastPanel` into the existing intelligence sidebar, same position/style as the other STEP 4/5 panels |
| `frontend/VARUNA-frontend_yash/lib/__tests__/forecast-panel-logic.test.ts` (new) | 5 tests proving the panel's render-guard never trusts a stale/mismatched value when status is not `produced` |

No file in `packages/varuna_pravaah/`, `packages/varuna_prativartan/`, or
`packages/varuna_integration/pipeline.py` was modified — PRAVAAH's
mathematics, `RealE2EPipeline`'s forecast stage logic, and
`GoldenCaseWorkflow` itself are all byte-for-byte unchanged from before
this task. Everything found was **proven**, not fixed, because nothing was
actually broken at the production-code level — the gap was in test
coverage and in the frontend's display surface.

## 4. Provider used

`varuna_pravaah.cube_provider.CubeBackedPravaahProvider` — real forward
particle drift against real CMEMS current fields. Confirmed by asserting
the provider's genuinely-written trajectory `.npz` file exists on disk
after each test run (`Path(forecast.trajectory_path).exists()`), not merely
that a `ForwardForecast` object was returned.

## 5. Replay behavior

`CASE-VALID` continues returning its hand-built `ForwardForecast` fixture
value, correctly labeled `engine_mode="replay"` /
`forecast.evidence_mode="real"` (per ADR-0012's already-established,
re-verified distinction). This is correct, not a gap: Phase 4's own text
permits using an existing fixture for the replay story precisely because no
replay fixture computes real drift by construction. The frontend's new
`ForecastPanel` renders this fixture's landfall/horizon data honestly today,
and will render a REAL PRAVAAH computation identically the moment a case is
served through a route backed by `GoldenCaseWorkflow.run_case()` with real
forcing.

## 6. Real-data behavior

Verified against real MC20 CMEMS/ERA5 forcing (`GoldenCaseWorkflow.run_case()`
+ `SimulatedSlickProvider`, the sanctioned no-GPU way to exercise the
PRODUCED path on a corpus whose frozen NETRA checkpoint currently finds
nothing — see STEP 0/2's own finding): forecast reaches `PRODUCED`, a real
trajectory file is written, `horizon_hours` matches configuration, and
`envelope.mode` correctly worsens to `SIMULATED` (never claims REAL) because
the input detection was simulated even though the forcing was real. A
genuinely-missing-forcing case (no event manifest at all) was verified to
fail closed: `GoldenCaseWorkflow.run_case()` raises, the `Case` transitions
to `FAILED` with a real, named error — never a silent empty success and
never a fabricated forecast.

## 7. Provenance

Verified present on every real forecast: `envelope.case_id`,
`envelope.provenance`, `envelope.mode`, `horizon_hours`, `trajectory_path`
(a real file), `computed_at`. All survive `build_product_case()`'s
composition unmodified — the same object, not a re-derivation.

## 8. EvidenceMode

Verified in both directions: real forcing + simulated detection → forecast
correctly reports SIMULATED (never falsely REAL); this holds both at the
raw `CaseResult`/stage level and, newly, after `build_product_case()`
composition specifically (the gap this task closes).

## 9. Tests

- `tests/integration/test_pravaah_canonical_product_case.py`: 9/9 passing.
- `frontend/.../lib/__tests__/forecast-panel-logic.test.ts`: 5/5 passing
  (new file; frontend suite total now 11/11 passing).
- Pre-existing PRAVAAH-relevant suites re-run, unmodified, all still
  passing: `test_pravaah_pipeline_integration.py`,
  `test_golden_case_engine_mc20_e2e.py`, `test_product_case_composition.py`.
- Full backend regression: **766 passed, 10 skipped, 1 pre-existing
  failure** (`test_netra_training_loop`, unrelated). Baseline before this
  task: 757/10/1. +9 net, zero regressions.
- Frontend: `npx tsc --noEmit` 0 errors, `npm run build` 0 errors (14/14
  routes), `npm run test` 11/11 passing.

## 10. Remaining limitations

1. **No route currently serves a real (non-replay, non-`SimulatedSlickProvider`)
   PRAVAAH forecast to the frontend.** `GET /v1/replay/{fixture}` only ever
   returns replay-fixture data; there is no `GET` route wired to
   `GoldenCaseWorkflow.run_case()` with real forcing + a real/simulated
   detection for the frontend to fetch. This is a live-API-orchestration
   concern, explicitly out of this task's scope (§ DO NOT list).
2. **MC20's frozen NETRA checkpoint still finds nothing on this corpus** —
   this task did not attempt to change that (out of scope: no NETRA
   training/model changes). The `SimulatedSlickProvider` path used here is
   the sanctioned way to test PRAVAAH without waiting on that separate,
   already-tracked research question.
3. **`ForecastPanel`'s trajectory is shown only as a filename**, not
   plotted on the map — this task's Phase 6 explicitly scoped verification
   to "do not redesign the frontend," and a real trajectory plot would be a
   map-layer feature, named here as a natural follow-on rather than
   attempted.
