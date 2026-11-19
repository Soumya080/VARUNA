# PRAVAAH Canonical Case Integration Report

**Run date:** 1 Sep 2026 · **Author:** router-datasets-55 · **Branch:** `feat/netra-real-training`
**NETRA status during this task:** v0.3 domain-expansion pilot training active throughout (GPU
98–100% util observed at task start and end). Not touched, queried invasively, paused, or
restarted. All work in this task is CPU-only.

## 1. Previous state

PRAVAAH was **already wired** into the canonical pipeline (`RealE2EPipeline._forecast()`,
`packages/varuna_integration/pipeline.py`), contrary to a prior audit's claim that it was
implemented-but-not-integrated. See `docs/architecture/PRAVAAH_CASE_INTEGRATION.md` §"Previous
state" for the correction and its evidence. This task's actual job turned out to be **verification
plus two scoped bug fixes** inside the existing integration point, not new wiring.

## 2. Integration point

`RealE2EPipeline._forecast(run, forcing_res, detection_res, validity_res)`, called from `.run()`
in stage order `... validity → forecast → decision ...`. Reached by both
`GoldenCaseWorkflow.run_case()` (REAL/SIMULATED) — REPLAY uses canned fixtures instead, by design.
Full call graph and input contract in the architecture doc.

## 3. Inputs (verified against the actual method, not assumed)

- Real `EventForcing` (`cmems_cube`, current-field grids) — required.
- `SlickDetection` (centroid, bbox, observation_time) — required; **not** `PhiField`/origin.
- `forecast_horizon_hours` from `PipelineConfig` (default 24.0h).
- `case_id` from `run.case_id`.
- No wind field, no fallback values invented for any input.

## 4. Real / Simulated / Unavailable semantics

Two real defects found and fixed, both verified against real MC20 CMEMS forcing:

1. **`case_id` was `None` on every forecast envelope.** Root cause: `forcing.envelope.case_id` is
   never set by `load_event_forcing()` (case_id isn't in scope at that point), and
   `EvidenceEnvelope.derive()` always inherits `case_id` from its caller with no override. Fixed
   with a local `.model_copy(update={"case_id": run.case_id})` inside `_forecast()` only — does not
   mutate the shared `EventForcing.envelope` object other stages read, and does not touch
   `_reconstruct()`/`_attribute()` (Track 2 territory, out of scope, flagged as a shared
   pre-existing gap).

2. **`ForwardForecast.envelope.mode` did not worsen with the detection's evidence mode** — it
   derived only from `forcing.envelope`, so a `SIMULATED` detection drifted through real CMEMS
   forcing produced a forecast whose own envelope incorrectly claimed `REAL`, disagreeing with the
   correctly-computed `StageResult.evidence_mode` for the same stage. **Found by this task's own
   new test failing on first write**, not discovered by inspection alone. Fixed by deriving with
   `also_from=[detection_env]`, mirroring the pattern `_reconstruct()` already uses for the
   identical purpose.

Verified truth table (real MC20 data):

| forcing mode | detection mode | `forecast.envelope.mode` (after fix) |
|---|---|---|
| REAL | REAL | REAL |
| REAL | SIMULATED | SIMULATED |

`MockPravaahProvider` (not used by the canonical pipeline, which always constructs
`CubeBackedPravaahProvider`) remains unconditionally SIMULATED per the prior session's ADR-0009 fix
— re-verified unchanged (`tests/unit/test_pravaah_mock.py` still green).

## 5. Output

Real fields verified present on a produced `ForwardForecast` (real MC20 run, `SimulatedSlickProvider`
detection to avoid GPU/NETRA contention — see §6):

```
forecast_id: fcast-cube-sim-b50b0bb1
horizon_hours: 24.0
n_landfalls: 1
trajectory_path: <exists on disk, real particle-position .npz>
envelope.mode: simulated   (correctly worsened from REAL forcing + SIMULATED detection)
envelope.case_id: OPVIEW-DEMO-01   (correctly propagated -- was None before this task's fix)
envelope.provenance: source_id='pravaah_cube_provider', ...
```

No `impact_probability`/`exposure_map`/`uncertainty` fields exist on `ForwardForecast` — not
invented here, per explicit instruction not to add fields to match the architecture diagram beyond
what PRAVAAH actually computes (`landfalls`, `horizon_hours`, `trajectory_path`).

## 6. Validity interaction

Unchanged. `_forecast()` receives `validity_res` and does not branch on it; the gate is not
consulted by and does not consult PRAVAAH. Confirmed via
`tests/unit/test_pravaah_pipeline_integration.py::test_forecast_signature_does_not_take_phi_or_origin`
(pins the method's actual parameter set) and the pre-existing
`tests/unit/test_replay_fixtures.py::test_case_blocked_is_a_scoped_break_not_a_blanket_one`
(PRATIVARTAN `BLOCKED` does not block forecast).

## 7. Replay behavior

REPLAY fixtures use a canned `ForwardForecast` (a different `_forecast()` helper, in
`replay_fixtures.py`, unrelated to the pipeline method of the same name) — this is correct by
design (REPLAY ≠ live re-execution). `CASE-VALID`/`CASE-SIMULATED`/`CASE-BLOCKED` all populate a
forecast stage; existing tests (`tests/unit/test_replay_fixtures.py`) already covered this and were
re-run, unchanged, green.

## 8. MC20 behavior

The real MC20 case (frozen v0.2 checkpoint) reports `NO_SLICK_DETECTED` — a real null result, not
altered. `_forecast()` correctly returns `NOT_YET_PRODUCED` / `NO_SLICK_TO_FORECAST`, chaining the
upstream reason. **No forecast was fabricated.** To verify the `PRODUCED` path against real MC20
forcing without spending GPU time on the currently-training NETRA v0.3 job, this task used
`SimulatedSlickProvider` (a non-GPU, non-NETRA detection stand-in already used by the project's own
`test_golden_case_engine_mc20_e2e.py` before this task) — confirmed to produce a real,
correctly-`SIMULATED`-labelled forecast against real CMEMS current data.

## 9. Error / boundary testing (Phase 9, all 7 scenarios)

| # | Scenario | Result | Test |
|---|---|---|---|
| 1 | Valid real current field | `PRODUCED`, REAL envelope | `test_real_forcing_plus_real_detection_produces_real_forecast_with_case_id` |
| 2 | Missing current field / forcing | `BLOCKED`, names "forcing" | `test_forcing_not_produced_blocks_forecast_naming_the_upstream_stage` |
| 3 | Out-of-domain current field | Freezes mid-trajectory, does not crash | pre-existing `tests/unit/test_pravaah_cube_provider.py::test_out_of_domain_mid_trajectory_freezes_not_crashes` (re-run, still green) |
| 4 | Unavailable forcing | Same as #2 (forcing not produced is the unavailable case at this stage) | as #2 |
| 5 | Simulated provider | `MockPravaahProvider` always SIMULATED regardless of input | pre-existing `tests/unit/test_pravaah_mock.py::test_forecast_envelope_is_simulated_even_when_input_envelope_claims_real` (re-run, still green) |
| 6 | Missing origin (Φ) | Not a dependency — forecast runs independent of Φ/validity by design | `test_forecast_signature_does_not_take_phi_or_origin`, pre-existing `test_case_blocked_is_a_scoped_break_not_a_blanket_one` |
| 7 | Malformed upstream result | **Found and fixed**: `detection_res.value[0]` on an empty-but-PRODUCED list previously raised an uncaught `IndexError`; now fails closed with `MALFORMED_DETECTION_RESULT` | `test_detection_produced_but_empty_value_list_fails_closed_not_indexerror` (new) |

No hidden synthetic fallback was found or introduced in any scenario.

## 10. OperatorCase

Verified end to end via a live `GoldenCaseWorkflow.run_case()` → `.to_operator_case()` call against
real MC20 forcing (`SimulatedSlickProvider` detection):

```
oc.case_id:               OPVIEW-DEMO-01
oc.forecast.status:       produced
oc.forecast.evidence_mode: simulated
oc.forecast.value:        ForwardForecast(forecast_id=..., envelope.case_id=OPVIEW-DEMO-01,
                            envelope.mode=simulated, envelope.provenance=<present>,
                            horizon_hours=24.0, n_landfalls=1)
```

All four required fields (forecast status, `ForwardForecast` payload, `EvidenceMode`, provenance,
case_id) are present and correct. Frontend not touched, not inspected beyond confirming the API
schema serializes (per this task's explicit "frontend owned by another engineer" boundary).

## 11. Tests

New: `tests/unit/test_pravaah_pipeline_integration.py` (6 tests — forcing-missing, detection-absent,
malformed-detection regression, PRAVAAH-exception, signature/no-Φ-dependency, real MC20 positive
path) + 1 new test appended to
`tests/integration/test_golden_case_engine_mc20_e2e.py` (the SIMULATED-worsening regression that
found Defect 2). All pass.

Full re-run of every directly and adjacently affected suite:
`tests/unit/test_track4_boundaries.py`, `test_golden_case_engine.py`, `test_replay_fixtures.py`,
`test_pravaah_mock.py`, `test_pravaah_cube_provider.py`, `test_pravaah_pipeline_integration.py`,
`tests/integration/test_track4_mc20_e2e.py`, `test_golden_case_engine_mc20_e2e.py`,
`tests/contract/*` — **193 passed, 0 failed.**

Full repository regression (`tests/unit tests/contract tests/integration tests/e2e`):

**583 passed, 10 skipped, 1 failed** (475s). The 1 failure
(`tests/unit/test_netra_training.py::test_netra_training_loop`,
`TypeError: 'NetraSample' object is not subscriptable`, `trainer.py:250`) is the same
pre-existing, NETRA-owned failure observed in every prior audit this session and untouched by
this task. +7 tests vs. the prior known-good baseline (576 passed) — exactly the 6 new tests in
`test_pravaah_pipeline_integration.py` plus the 1 appended to
`test_golden_case_engine_mc20_e2e.py`. Zero new failures introduced.

No unrelated test was weakened, skipped, or modified to pass.

## 12. Runtime / performance (measured, not optimized)

| Measurement | Value |
|---|---|
| Real forcing load (`load_event_forcing`, ERA5+CMEMS, MC20) | 5.93s |
| `CubeBackedPravaahProvider.forecast_drift()` (50 particles, 96 steps at 24h horizon) | 0.64s |
| Python-tracked memory (forcing load + one forecast) | 104.6MB current / 107.2MB peak |

No optimization was performed — these numbers did not surface an integration issue requiring one.

## 13. Documentation

- `docs/architecture/PRAVAAH_CASE_INTEGRATION.md` — call graph, input contract, both defects with
  root cause and fix, real/simulated semantics table, validity interaction, replay/MC20 behavior,
  limitations.
- This report.

## Safety

```
deleted = 0
moved = 0
renamed = 0
overwritten = 0
frontend modified = 0
NETRA training modified = 0
NETRA checkpoint modified = 0
NETRA Gold modified = 0
Track 2 scientific implementation (PRATIVARTAN/NYAYA math, validity thresholds) modified = 0
MC20 Gold modified = 0
official test modified = 0
```

Files touched: `packages/varuna_integration/pipeline.py` (the one integration point, ~35 net new
lines across the two fixes), 1 new test file, 1 amended test file, 2 new docs. Nothing else.

## Final status

**PRAVAAH_CANONICAL_INTEGRATION_READY**

All stop-condition items satisfied:
- [x] PRAVAAH is invoked by canonical Case Engine (was already true; re-confirmed)
- [x] real CMEMS path works (measured, timed)
- [x] `ForwardForecast` is attached to `CaseResult` (via `case.metadata["forecast"]`, generic stage mapping)
- [x] EvidenceMode correct (Defect 2 fixed and tested)
- [x] provenance correct (was already correct)
- [x] case_id correct (Defect 1 fixed and tested)
- [x] replay case produces forecast (pre-existing, re-confirmed)
- [x] MC20 does not fabricate a forecast (confirmed: real null propagates honestly)
- [x] OperatorCase serializes forecast correctly (confirmed live, end to end)
- [x] focused tests pass (7 new + all adjacent suites green)
- [x] documentation complete
