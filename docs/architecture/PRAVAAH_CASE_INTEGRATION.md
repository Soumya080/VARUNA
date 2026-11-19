# PRAVAAH Canonical Case Integration

**Status:** Integration confirmed and hardened, not built from scratch · **Date:** 1 Sep 2026

## Previous state — corrected from a prior audit

The previous project-status audit (`reports/project/VARUNA_FINAL_PROJECT_STATUS.md`, §9) stated
PRAVAAH was "implemented and unit-tested in isolation, not yet load-bearing in the live per-case
pipeline." **That was inaccurate**, and this document corrects it with evidence: PRAVAAH was
already wired into `RealE2EPipeline._forecast()` (`packages/varuna_integration/pipeline.py`) —
confirmed by `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md`'s own ownership table, which
already lists "Forecast (PRAVAAH) | `pipeline._forecast()` | Unchanged," and by the real MC20 run
artifact `reports/mc20_track4_e2e_run.json`, whose `forecast` stage already carries a
`NO_SLICK_TO_FORECAST` reason produced by that exact code path. The prior audit's PRAVAAH section
should have carried this forward; it did not, and that was this session's error to correct, not a
change in the underlying system.

What this task actually found and fixed were two real, narrow defects in that already-wired
integration point — not a missing integration.

## Call graph (as actually executed, confirmed by reading `RealE2EPipeline.run()`)

```
Case (case_id resolved) ──▶ forcing (ERA5+CMEMS)
                              │
                              ▼
                       netra_detection ──▶ ais_ingest
                              │
                              ▼
                     phi_reconstruction (PRATIVARTAN)
                              │
                              ▼
                        attribution (NYAYA)
                              │
                              ▼
                          validity (Gate)
                              │
                              ▼
                    forecast (PRAVAAH)  ◀── depends on: forcing + netra_detection ONLY
                              │             (NOT on phi_reconstruction/validity — see below)
                              ▼
                      decision (ABHIYAN)
                              │
                              ▼
                           mission ──▶ alerts ──▶ OperatorCase
```

**PRAVAAH does not depend on Φ/origin or the Validity Gate.** `_forecast(run, forcing_res,
detection_res, validity_res)` reads `validity_res` only to pass through untouched — it is not
consulted. This is a structural fact of the existing architecture, not something this task changed:
forward drift starts from the **detected slick's own position** (`detection.centroid`), a forward
question ("where does this go"), which is independent of PRATIVARTAN's backward-reconstructed
origin ("where did this come from"). Proof: `tests/unit/test_replay_fixtures.py::
test_case_blocked_is_a_scoped_break_not_a_blanket_one` already asserted a PRATIVARTAN `BLOCKED`
does not block `forecast`; this task added
`tests/unit/test_pravaah_pipeline_integration.py::test_forecast_signature_does_not_take_phi_or_origin`
to pin the method signature itself, so a future change that silently added a Φ dependency would be
caught.

No new pipeline was created. No new orchestration surface was added. Both defects fixed below are
line-level changes inside the one existing `_forecast()` method.

## Input contract (verified, not invented)

| Input | Source | Required? |
|---|---|---|
| `forcing_res.value` (`EventForcing`: `cmems_cube`, `current_field._u_grid/_v_grid`) | `varuna_integration.forcing.load_event_forcing()` | Yes — `BLOCKED` if not produced |
| `detection_res.value[0]` (`SlickDetection`: centroid, bbox, observation_time) | `NetraDetectionBoundary.detect_tiles()` | Yes — `NOT_YET_PRODUCED` if absent |
| `forecast_horizon_hours` | `PipelineConfig` (default 24.0h) | Yes, has a default |
| `envelope` | Derived from `forcing.envelope` + a `detection`-mode envelope (fixed this task, see below) | Yes |
| `case_id` | `run.case_id` (the `PipelineRun`'s own identity) | Yes, now propagated (fixed this task) |
| Wind field | **Not used.** `CubeBackedPravaahProvider` drives drift from the current field only. | N/A — not invented |

No fallback values were invented for any of these — a missing input produces a named `BLOCKED` or
`NOT_YET_PRODUCED` result, never a substituted default.

## What was already correct (verified, not re-implemented)

- `CubeBackedPravaahProvider.forecast_drift()` runs real advection against the real gridded CMEMS
  current field (`velocity_at()`), fails closed (freezes rather than extrapolates) on an
  out-of-domain mid-trajectory query.
- `MockPravaahProvider` unconditionally reports `EvidenceMode.SIMULATED` regardless of its input
  envelope (ADR-0009, fixed in the prior Track 2 session) — not touched again here, still correct.
- The stage-level `StageResult.evidence_mode` was already correctly computed as
  `worst_mode(forcing_res.evidence_mode, detection_res.evidence_mode)`.
- `case_bridge.py`'s `STAGE_TO_METADATA_KEY` already maps `"forecast" → "forecast"` generically —
  no special-casing needed for PRAVAAH to reach `case.metadata["forecast"]`.
- `golden_case_engine.py`'s `STAGE_ORDER`/`STAGE_TO_STATUS` already include `"forecast"` /
  `CaseStatus.FORECASTING` — the lifecycle projection already accounted for this stage.

## Two real defects found and fixed (both inside `_forecast()`, both this task's scope)

### Defect 1 — `case_id` was silently dropped

`forcing.envelope` is built by `load_event_forcing(gold_dir)` before any `case_id` is in scope
(reproduced directly: `load_event_forcing(...).value.envelope.case_id` is `None` on the real MC20
corpus). `EvidenceEnvelope.derive()` always inherits `case_id` from `self` (no override parameter
exists, by ADR-0006 design), so every envelope derived from `forcing.envelope` — including, before
this fix, the one attached to `ForwardForecast` — carried `case_id=None`.

**Fix:** `_forecast()` now builds `forcing.envelope.model_copy(update={"case_id": run.case_id})`
before deriving, so `ForwardForecast.envelope.case_id` correctly carries the real case identity.
This is a local copy — it does **not** mutate the shared `EventForcing.envelope` object that
`_reconstruct()`/`_attribute()` also read, so this fix has zero effect outside the forecast stage.

**Scope note:** `_reconstruct()` and `_attribute()` share the identical `case_id=None` root cause
(they also derive from `forcing.envelope`). This was **not** fixed here — doing so would touch
PRATIVARTAN/NYAYA stage code, which is Track 2's frozen territory and outside this task's PRAVAAH
mandate. Flagged as a named, open, out-of-scope item.

### Defect 2 — `ForwardForecast.envelope.mode` did not worsen with the detection's mode

Before this fix, `parent = forcing.envelope.derive(artifact_id=..., produced_by=...)` derived
**only** from `forcing.envelope` — the detection's own evidence mode was never passed via
`also_from`. Consequence: a `SIMULATED` detection (e.g. `SimulatedSlickProvider` on real MC20
forcing) drifted through a real current field produced a `ForwardForecast` whose own `envelope.mode`
incorrectly read `REAL`, while the separately-computed `StageResult.evidence_mode` for the same
stage correctly read `SIMULATED` — **two disagreeing answers to "how real is this artifact,"**
found by this task's own test
(`tests/integration/test_golden_case_engine_mc20_e2e.py::
test_pravaah_forecast_runs_on_real_mc20_forcing_via_the_canonical_pipeline`, which failed on first
write, exposing this).

**Fix:** build a `detection`-mode `EvidenceEnvelope` (mirroring the pattern `_reconstruct()` already
uses for the identical purpose) and pass it via `also_from=[detection_env]` to the `derive()` call,
so the forecast's own envelope now worsens correctly: `REAL forcing + SIMULATED detection →
SIMULATED forecast`, matching ADR-0006's monotonic-worsening rule and the stage-level record.

Both fixes verified against real MC20 CMEMS forcing (not a synthetic fixture) — see the Tests
section of `reports/pravaah/PRAVAAH_CASE_INTEGRATION_REPORT.md`.

## Real / Simulated / Unavailable semantics (verified)

| Scenario | `forcing_res.evidence_mode` | `detection_res.evidence_mode` | `forecast.envelope.mode` (now) |
|---|---|---|---|
| Real CMEMS current field + real (frozen-checkpoint) detection | REAL | REAL | **REAL** |
| Real CMEMS + `SimulatedSlickProvider` | REAL | SIMULATED | **SIMULATED** (was incorrectly REAL before this fix) |
| Missing/insufficient forcing | n/a (stage `BLOCKED`) | — | forecast stage `BLOCKED`, no `ForwardForecast` object exists |
| `MockPravaahProvider` used directly (not via the canonical pipeline, which always uses `CubeBackedPravaahProvider`) | any | any | **SIMULATED**, unconditionally (ADR-0009, prior session) |

Never observed and explicitly tested against: a `REAL`-labelled failure silently becoming a
`SIMULATED` success, or `EvidenceMode` inferred from a provider's class name rather than from the
envelope chain.

## Validity Gate interaction — unchanged, confirmed unchanged

The Validity Gate was **not modified** by this task. `_forecast()` receives `validity_res` and does
not branch on it — a `RESTRICTED` or `INCONCLUSIVE` gate verdict does not block PRAVAAH from
running, and PRAVAAH's success does not change the gate's verdict. This separation was already
correct (`ValidityState`/`StageStatus`/`EvidenceMode` remain three independent vocabularies per
`CASE_ORCHESTRATION_RECONCILIATION.md` §4) and is unchanged here. If forecast legitimately cannot be
produced, the pipeline returns the repository's existing canonical states
(`NOT_YET_PRODUCED`/`BLOCKED`) with a named reason — never a fabricated forecast.

## Replay behavior

REPLAY fixtures (`packages/varuna_domain/replay_fixtures.py`) construct a **canned**
`ForwardForecast` via a helper (`_forecast()` in that module, unrelated to and not to be confused
with `pipeline._forecast()`), not a live PRAVAAH execution — this is correct and by design: REPLAY
demonstrates the schema/envelope contract with deterministic canned values, it does not re-run the
engine. `CASE-VALID`, `CASE-SIMULATED`, and `CASE-BLOCKED` fixtures each populate a forecast stage;
`test_case_blocked_is_a_scoped_break_not_a_blanket_one` already proves the PRATIVARTAN-independence
property at the replay level too.

## MC20 behavior

The real, current MC20 case (frozen NETRA v0.2 checkpoint) finds `NO_SLICK_DETECTED` — a real null
result, not altered by this task. `_forecast()` therefore correctly returns
`NOT_YET_PRODUCED` / `NO_SLICK_TO_FORECAST`, chaining the upstream detection reason through rather
than dropping it. No forecast was fabricated to make a demo look richer. Separately, because NETRA
v0.3 is training and re-running the frozen checkpoint would cost GPU time this task was told not to
spend, this task instead exercised the `PRODUCED` path against real MC20 forcing using
`SimulatedSlickProvider` (which does not touch NETRA or the GPU) — the same substitution the
project's own `test_golden_case_engine_mc20_e2e.py` already used before this task, not a new
shortcut invented here.

## Remaining limitations (disclosed, not fixed here)

- `_reconstruct()`/`_attribute()` share the same `case_id=None` root cause as Defect 1 above —
  out of scope (Track 2 frozen).
- No wind field is consulted by `CubeBackedPravaahProvider` — current-only advection, matching the
  provider's own documented design, not a gap this task introduced or is positioned to close.
- No impact/exposure map or uncertainty quantification exists on `ForwardForecast` beyond
  `landfalls` — not invented here, per the explicit instruction not to add fields just to match the
  architecture diagram.
- ABHIYAN's `_decide()` does not currently consume the forecast's content (it reads `phi_res`,
  `validity_res` only) — unchanged by this task; flagged as a possible future integration, not
  executed here (would expand scope beyond "wire PRAVAAH into the case engine").
