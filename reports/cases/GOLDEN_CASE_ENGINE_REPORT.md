# Golden Case Engine — Report

**Status: CASE_ENGINE_READY**

Safety: `deleted=0 moved=0 renamed=0 overwritten=0` — verified by `git status`
before and after every change; the only pre-existing file touched
(`packages/varuna_domain/entities.py`) received a pure, additive diff
(`26 insertions(+), 0 deletions(-)`). NETRA training/checkpoints/Gold/GPU were
never touched.

---

## What this actually is

Before writing anything, two peer sessions were consulted (their answers are
the basis for the design below, not assumed):

- **`router-datasets-ca`** had already built the real ten-stage producer
  chain (`packages/varuna_integration/pipeline.py::RealE2EPipeline`) — real
  NETRA boundary with a checkpoint-freeze gate, real ERA5/CMEMS forcing, real
  AIS, honest `StageStatus`/`EvidenceMode` propagation — but it is
  **event-scoped, not case-scoped** (`run(gold_dir, case_id=None)`), has no
  lifecycle state machine (only per-stage `StageStatus`), and no idempotency
  (`run_id` is unique by construction on every call).
- **`packages/varuna_domain/case_workflow.py`** (predates Track 4) already had
  the other half: `CaseStatus` lifecycle, persistence, artifacts, events — but
  takes slick points as raw input with no detection stage, and always runs
  synthetic forcing under a hardcoded `SIMULATED` envelope.

Per `router-datasets-ca`'s own words: *"Your task is the union: CaseWorkflow's
state machine and persistence, driven by varuna_integration's producer
boundaries and evidence discipline... a third [path] would make the API
surface incoherent."* That is exactly what was built. **Nothing here
duplicates a schema or reimplements a producer.**

## What was built

| File | What it is |
|---|---|
| `packages/varuna_domain/golden_case_engine.py` | The canonical runner: `GoldenCaseWorkflow.run_case()` (REAL/SIMULATED, via `RealE2EPipeline`, unmodified) and `.run_replay_case()` (REPLAY, via canned fixtures) — one class, one lifecycle, one reproducibility/idempotency path (`_finalize()`) for both. |
| `packages/varuna_domain/replay_fixtures.py` | Six deterministic `CASE-*` fixtures, built from the real typed contracts (`PhiField`, `AttributionResultV2`, `ValidityGateResult` via the real `evaluate_validity_gate()`, `ForwardForecast`, `AssetTasking`, `MissionRecord`, `DeliveryResult`) and the real `PipelineRun.record()`/`blocked_by()` cascade methods. No network, no GPU, no filesystem outside the process. |
| `packages/varuna_domain/entities.py` | Additive only: `CaseStatus` gains `CASE_CREATED/INGESTED/DETECTING/.../COMPLETE/BLOCKED/UNAVAILABLE/OOD`. Every pre-existing member is untouched. |
| `tests/unit/test_golden_case_engine.py` | 21 tests: reproducibility, lifecycle, idempotency, BLOCKED-vs-UNAVAILABLE, OperatorCase projection. |
| `tests/unit/test_replay_fixtures.py` | 22 tests: all six fixtures build, terminal status per fixture, determinism, JSON-safety, monotonic evidence mode. |
| `tests/unit/test_golden_case_engine_fail_closed.py` | 6 tests, one per required fail-closed property (see below). |
| `tests/integration/test_golden_case_engine_mc20_e2e.py` | 5 tests against the real MC20 Event Gold (skips cleanly if absent) — proves the REAL/SIMULATED path, not just REPLAY, at the same bounded scale as the existing Track 4 test. |

**All 55 new unit tests + 5 integration tests pass.** The full pre-existing
`tests/unit` suite (434 tests, excluding heavy NETRA training tests) and the
targeted case-related suites (`tests/api`, `tests/integration/test_case_0001.py`,
`tests/regression/test_golden_cases.py`, `tests/contract/test_operator_case.py`,
`tests/unit/test_track4_boundaries.py`, 79 tests) still pass — **zero
regressions**.

## Case lifecycle

```
CASE_CREATED -> INGESTED -> DETECTING -> RECONSTRUCTING -> ATTRIBUTING
             -> VALIDATING -> FORECASTING -> DECIDING -> MISSION -> ALERTING -> COMPLETE
                                                    (or BLOCKED / UNAVAILABLE / OOD / FAILED)
```

`derive_case_status()` (`golden_case_engine.py`) is the single place a
`PipelineRun` becomes a terminal `CaseStatus`. It deliberately answers a
different question from `StageStatus`: **whether the case, as a whole,
finished its intended traversal**, not whether every stage found a positive
result. A restrictive gate correctly withholding tasking is `COMPLETE`, not a
failure — that judgment already exists in `RealE2EPipeline`'s own module
docstring, and this function inherits it rather than re-litigating it.
Per-section outcome (what was actually found) is read from the OperatorCase
view's per-section `status`/`evidence_mode`, not from `case.status`.

**BLOCKED vs UNAVAILABLE** — both stem from a `StageStatus.BLOCKED`
somewhere in the run, but answer different questions: if the *first* broken
stage is `forcing` or `ais_ingest` (the observation-ingestion layer), the case
never had usable input — that's `UNAVAILABLE`, a data-availability fact, not
a system defect. Anything blocked further downstream, on otherwise-good
input, is a genuine integration break — `BLOCKED`. Proven distinct by
`test_blocked_and_unavailable_are_distinguished_by_root_cause`.

`OOD` is read from `StageResult.detail["ood"]` if a detector ever sets it.
**No detector in this codebase sets it today** — the real MC20 checkpoint's
null result is documented as `detection unavailable — input outside training
distribution`, explicitly *not* a proven OOD finding
(`docs/e2e/MC20_REAL_E2E_INTEGRATION.md`). `CASE-OOD` is therefore a REPLAY
fixture only, showing what the engine does if a detector one day reports OOD
explicitly — not a claim about MC20 today.

## DetectorProvider boundary

Reused, not re-cut: `NetraProvider` (ABC) + `NetraDetectionBoundary` +
`resolve_netra_boundary()` (`packages/varuna_integration/netra_boundary.py`,
owned by `router-datasets-ca`, not touched). It already carries `model_id`
(derived), `model_version`, a checkpoint-freeze sha256 (`checkpoint_hash`),
detection state, evidence mode and provenance — enforced structurally: a
checkpoint without a verified `.frozen.json` sidecar cannot serve real
inference, and `SimulatedSlickProvider` can never be labelled `REAL`.

`detector_provider_info()` (`golden_case_engine.py`) reads all of this off
whatever the detection stage actually recorded. One field is a real,
documented gap, flagged by `router-datasets-ca` directly and **not silently
invented**: `preprocessing_version` is not tracked by the boundary itself
today. It is reported as the one value the golden engine actually knows —
`ASSUMED_NETRA_PREPROCESSING_VERSION = "netra-norm-v0.2-nodata-excluded"`
(the frozen Gold v0.2 normalization contract every MC20 tile is preprocessed
under) — explicitly labelled ASSUMED, not measured. Wiring real
per-checkpoint preprocessing-version tracking into `netra_boundary.py` is a
P1 follow-on for that boundary's owner, not done here (would touch a file
`router-datasets-ca` owns).

## REPLAY fixtures

| Fixture | Terminal `CaseStatus` | What it proves |
|---|---|---|
| `CASE-VALID` | `COMPLETE` | Full chain, gate genuinely `VALID` (`evaluate_validity_gate()` run for real against a synthetic `PhiField` that DOES carry a `SensitivityBlock`), mission + alert produced. |
| `CASE-RESTRICTED` | `COMPLETE` | Gate `RESTRICTED` because `phi.sensitivity is None` — the **real, currently-shipping** default (ADR-0007's sensitivity sweep is unimplemented, `phi_builder.py` TODO(P1)) — not a fabricated restriction. Decision/mission correctly `NOT_YET_PRODUCED`; alerts still fire (validity-only precondition, matching `_alerts()`'s real logic). |
| `CASE-OOD` | `OOD` | Detector reports `detail["ood"]=True`; nothing downstream (phi/attribution/validity/decision/mission/alerts) executes past that point. |
| `CASE-UNAVAILABLE` | `UNAVAILABLE` | Forcing **and** AIS both genuinely unavailable (missing cube/join files) — root cause is missing input, not a break. |
| `CASE-SIMULATED` | `COMPLETE` | REAL forcing + REAL AIS + explicitly-requested SIMULATED detection. Evidence mode worsens monotonically from detection onward (pinned by `test_no_stage_claims_real_evidence_from_canned_data_incorrectly`); gate lands `DEGRADED` (simulated evidence is a caveat, not a block) and the chain still completes. |
| `CASE-BLOCKED` | `BLOCKED` | Forcing/AIS/detection all succeed on good input; PRATIVARTAN raises. Proven **scoped**, not blanket: `forecast` (which does not depend on PRATIVARTAN) still PRODUCES — `test_case_blocked_is_a_scoped_break_not_a_blanket_one`. |

Determinism: `test_deterministic_modulo_run_id_and_timestamps` builds each
fixture twice and diffs the serialized output with only `run_id` and
wall-clock fields excluded — byte-identical.

## Fail-closed proofs (one test per required property)

| Property | Test |
|---|---|
| missing observation → no false detection | `test_missing_observation_yields_no_false_detection` |
| detector OOD → no trustworthy detection | `test_detector_ood_yields_no_trustworthy_detection` |
| missing AIS → attribution constrained | `test_missing_ais_constrains_attribution` |
| invalid Phi → validity blocked/restricted | `test_invalid_phi_blocks_or_restricts_validity` |
| blocked validity → no mission | `test_blocked_validity_yields_no_mission` |
| unavailable forecast → no fabricated forecast | `test_unavailable_forcing_yields_no_fabricated_forecast` |

`tests/unit/test_golden_case_engine_fail_closed.py`.

## Idempotency

`GoldenCaseWorkflow._cached_result()` keys on `(case_id, config_hash)`.
`config_hash()` hashes every scientific tunable in `PipelineConfig` (particles,
ensemble, durations, seed, priors, corridor width, AIS status/limit, run
class) plus `gold_dir` — not the whole object graph, since a run_id or
timestamp changing must not defeat idempotency, but a different Gold version
or a different seed must.

- Re-running the same `case_id` + equal config: `idempotent_replay=True`, zero
  new events, zero new artifacts, zero new missions/alerts —
  `test_rerun_same_case_same_config_does_not_duplicate_missions_or_events`.
- `force=True` genuinely re-runs (new `run_id`, new events) —
  `test_force_rerun_creates_a_new_run`.
- A different fixture/config on the same `case_id` is correctly treated as a
  *different* run, not deduplicated against the wrong prior result —
  `test_different_fixtures_on_same_case_are_not_treated_as_the_same_run`.

## Reproducibility

Every run's `ReproducibilityRecord` (`golden_case_engine.py`) carries
`case_id`, `run_id`, `engine_mode`, `model_id`/`model_version`/
`checkpoint_hash`/`preprocessing_version` (from the DetectorProvider
boundary), `dataset_version` (read from the Gold manifest, `None` in REPLAY),
`config_hash`, `code_version` (real `git rev-parse HEAD`, degrades to
`"unknown"` outside a checkout rather than crashing), `evidence_mode`, and
both timestamps. Verified against the real MC20 checkout: `code_version` is
the actual current commit hash, `dataset_version="mc20_v0_1"` on the real Gold
integration test.

## Canonical output → OperatorCase v1

`CaseResult.to_operator_case(workflow)` calls
`apps.api.operator_case_view.build_operator_case(case, workflow)` — the
existing, unmodified projection — because `apply_run_to_case()`
(`varuna_integration/case_bridge.py`, also unmodified) already writes every
stage onto `Case.metadata` in the exact shape that projection reads. Verified
against both REPLAY (`CASE-SIMULATED`, `CASE-OOD`) and the real MC20
REAL/SIMULATED path — every section (`observation`/`detection`/`origin`/`ais`/
`attribution`/`validity`/`forecast`/`decision`/`mission`/`alerts`/
`evidence`/`provenance`) is producible through the golden engine with no
change to that file.

## What was deliberately NOT touched, and why

- `packages/varuna_integration/pipeline.py`, `netra_boundary.py`, `ais_source.py`,
  `forcing.py`, `case_bridge.py`, `apps/api/operator_case_view.py` — all
  reused unmodified. Two peer sessions (`router-datasets-ca`,
  `router-datasets-3f`) were coordinating live edits to `varuna_integration`
  and `operator_case_view.py` during this build; confirming scope up front
  (see coordination record below) avoided any collision, and in the end this
  engine needed zero edits to either file.
- `packages/varuna_missions/service.py`, `varuna_alerts/service.py` — reused
  as injected dependencies (`mission_service=`, `alert_service=`), not
  modified. `router-datasets-3f` independently found and fixed a real
  pre-existing `AVAILABLE -> ASSIGNED` transition bug in
  `MissionService.approve_and_assign()` during their own ABHIYAN/Mission/Alert
  task — noted here for anyone wiring real approval into the golden engine
  later, not re-fixed (already fixed by its owner).
- `packages/varuna_abhiyan/decision_state.py::derive_operational_decision_state()`
  and `packages/varuna_missions/lifecycle_view.py` (both new, from
  `router-datasets-3f`'s task) are **not** wired into the golden engine's
  `CaseResult` — they are a derived *view* over `ValidityState`/`MissionState`
  the OperatorCase projection already exposes, and integrating them is
  additive, optional polish, not required for `run_case()`/`run_replay_case()`
  to be correct. Flagged as a natural P1 follow-on (a `CaseResult.decision_state`
  convenience property) rather than done speculatively here.

## Cross-session coordination record

- `router-datasets-ca` answered five scoping questions before any code was
  written (pipeline maturity, lifecycle gap, DetectorProvider boundary
  identity, active-edit status, existing fixtures) and flagged two real
  behavioural facts load-bearing for fixture design: (1) NETRA detects
  nothing on real MC20 tiles today — any REAL fixture claiming a full chain
  completing on MC20 would be fiction; (2) a placeholder detection's
  `observation_time` must be the event's real acquisition time, or particle
  loss swings from 0% to 70% as an artefact of the clamp, not the physics.
  Both are respected: no REAL-mode fixture is claimed to complete on MC20 in
  this report, and every replay/test detection uses the fixed `2023-01-15`
  anchor time, never `datetime.now()`.
- `router-datasets-3f` (ABHIYAN/Mission/Alert task) confirmed no file-region
  overlap up front, then supplied the decision-state/mission-lifecycle
  mapping tables above as a P1 integration point.

## Limitations, stated plainly

- REPLAY fixtures are synthetic, deterministic, and explicitly labelled
  `SIMULATED`/worse in every non-`CASE-VALID` scenario; `CASE-VALID` itself
  is a hypothetical "if a frozen, calibrated checkpoint fired here" — not a
  claim about any real scene. None of the six fixtures assert anything about
  real oil at MC20 or anywhere else.
- `_ReplayedRunView` (returned on an idempotent cache hit) does not expose
  `.stages` — a caller that needs the full stage detail of the *original* run
  reads `case.metadata` (already written on the first, non-cached call and
  never overwritten by a cached replay), not the returned `run` object. This
  is intentional (re-exposing `.stages` would require reconstructing a live
  `PipelineRun`, i.e. re-running), but is a real ergonomic sharp edge worth a
  P1 convenience wrapper if callers hit it often.
- The `AVAILABLE -> ASSIGNED` two-step mission approval requirement (see
  `router-datasets-3f`'s note above) means `GoldenCaseWorkflow` never calls
  `approve_and_assign()` itself — missions are created `PROPOSED`/`AVAILABLE`
  only, matching `RealE2EPipeline`'s own documented "no asset is dispatched
  here" contract. Human authorization remains a deliberate, separate step.
- `Φ` sensitivity (`SensitivityBlock`) is genuinely unimplemented in
  production (ADR-0007 TODO(P1)); `CASE-VALID`'s hand-built sensitivity block
  demonstrates the gate's *mechanism*, not a claim that production PRATIVARTAN
  can produce one today. `CASE-RESTRICTED` is the honest current default.

## Commands

```bash
# Unit + fail-closed + replay-fixture suites
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=packages:. .venv/Scripts/python.exe \
  -m pytest tests/unit/test_golden_case_engine.py tests/unit/test_golden_case_engine_fail_closed.py \
            tests/unit/test_replay_fixtures.py -q

# Real MC20 integration test (skips cleanly if the Gold corpus is absent)
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=packages:. .venv/Scripts/python.exe \
  -m pytest tests/integration/test_golden_case_engine_mc20_e2e.py -q
```

---

**CASE_ENGINE_READY**
