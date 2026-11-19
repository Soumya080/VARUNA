# VARUNA GRID v2 — Final Project Status

**Audit type:** Read-only, evidence-driven · **Audit date:** 31 Aug 2026 · **Branch:** `feat/netra-real-training`
**Auditor role:** Principal Engineer / System Architect / Release Manager / Technical Auditor
**Audit safety:** files modified: 0 · files created: 1 (this report) · files deleted: 0 · files moved: 0 · files renamed: 0 · overwritten: 0

> This report trusts nothing it did not check. Every status line below is backed by a file, a test
> run, a process inspection, or a git artifact named next to it. Where prior reports were checked
> and found accurate, that is stated; where they could not be reconciled, that is stated too.

---

## 1. Executive Snapshot

| | |
|---|---|
| **Overall status** | Strong, real, partially-integrated prototype. Most core science (PRATIVARTAN, NYAYA, Validity, AIS) is real and tested; two real integration paths exist (`CaseWorkflow`, `GoldenCaseWorkflow`) that were reconciled this week rather than left competing; CHHAYA and the frontend are the weakest links. |
| **Hackathon readiness** | **Demoable with replay**, with real segments. See §21. |
| **Live processes right now** | NETRA v0.3 domain-expansion pilot training, GPU-bound. Nothing else (no API server, no frontend dev server, no DB/broker) is currently running. |
| **Biggest blocker** | No live backend/frontend process exists to click through right now — everything demoable today runs via scripts/tests, not a running stack. Second: CHHAYA has no real model, only a coverage heuristic. |
| **Estimated prototype completeness** | 66% (audit-based estimate; see §17 for the weighted breakdown — do not read this as a measured fact). |

---

## 2. 🔴 Live Runtime Status

# 🔴 LIVE NOW

| Process | State | Purpose | Runtime (at audit time) | Resource |
|---|---|---|---|---|
| NETRA v0.3 pilot training | 🔴 **RUNNING** | `scripts/netra_v03/07_train_v03_pilot.py --config configs/lab/netra_v03_domain_expansion.yaml`, run `pilot_01_run2`, epoch 4/30, step 3383 | ~2h43m elapsed (9805s per its own metrics log) | GPU: RTX 3060, 98% util, 5.3/12.3 GB VRAM (~3.68 GB reported by the training process itself) |
| Backend API (FastAPI/uvicorn) | ⚪ **STOPPED** | `apps/api` | — | — |
| Frontend dev server (Vite) | ⚪ **STOPPED** | `apps/web` | — | — |
| PostgreSQL | ⚪ **STOPPED / UNKNOWN** | case/artifact persistence | — | no listener on 5432 |
| Redis | ⚪ **STOPPED / UNKNOWN** | Celery broker | — | no listener on 6379 |
| MinIO | ⚪ **STOPPED / UNKNOWN** | object storage | — | no listener on 9000/9001 |
| Celery worker | ⚪ **STOPPED** | async task execution | — | — |

**Verification method:** `nvidia-smi`, `Get-CimInstance Win32_Process` (command-line inspection),
`Get-NetTCPConnection -State Listen` against the ports these services would normally bind
(8000/8080/3000/5173/5432/6379/9000/9001/5555) — none were listening at audit time. This is a
point-in-time observation; any of these can be started with `make up-infra` / `make run-api` /
`cd apps/web && npm run dev` without code changes (not run here — audit is read-only).

**Do not interfere:** the NETRA process above was not touched, queried invasively, killed, or
paused by this audit. Its own log/metrics files were read (not written).

---

## 3. 🏗 Target Architecture vs Actual Implementation

```
Data Sources ──► Data Guard ──► NETRA ──► PRATIVARTAN ──► NYAYA ──► CHHAYA ──► PRAVAAH ──► Validity ──► ABHIYAN ──► Mission ──► Alerts ──► OperatorCase ──► Dashboard
    ✅            🟢            🟡          🟢              🟢         🔴          🟢           🟢          🟢          🟢         🟢          🟢               🟡
```

Legend: ✅ actual (real, working) · 🟢 operationally ready · 🟡 partial · 🟠 integration required · 🔴 missing/blocking · ⚪ future/not started

Two real, honest orchestration paths exist rather than one canonical path with a competing
shadow — this was flagged as a risk and actively reconciled this week
(`docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md`, `reports/cases/GOLDEN_CASE_ENGINE_REPORT.md`):

- **`varuna_domain.CaseWorkflow`** — the older path. Owns lifecycle/persistence/PRAMAN/event
  spine. Takes slick points as *input* (no detection stage), and calls
  `reconstruct_origin()` with no real `current`/`wind` — **synthetic forcing only** on this path.
- **`varuna_integration.RealE2EPipeline` + `GoldenCaseWorkflow`** — the newer, now-canonical path
  (as of this week's reconciliation). Ten real producer stages, real ERA5/CMEMS forcing, real AIS,
  `NetraDetectionBoundary` freeze-verified checkpoint gate, full `EvidenceMode` propagation,
  idempotency keyed on `(case_id, config_hash)`, and a `deterministic_run_id`. This is the path
  that should be used going forward; `CaseWorkflow` was not deleted (nothing is deleted per this
  project's own convention) and remains directly callable.

Neither path was invented by this audit — this finding is verified against the documents named
above and against the actual call graph (`grep` for `CaseWorkflow(` / `GoldenCaseEngine` across
`apps/`, `tests/`, `scripts/`), not merely asserted from the docs.

---

## 4. 📊 Component Status Matrix

| Component | Status | Evidence | Real/Simulated | Integration |
|---|---|---|---|---|
| Sentinel-1/SAR ingestion | 🟢 | `packages/varuna_data_eng/preprocessing/sentinel1_grd_calibration.py`, MC20 real SAFE calibration validated (`reports/mc20_sar_calibration_validation.json`) | REAL | wired into MC20 Gold corpus |
| AIS ingestion | 🟢 | `packages/varuna_integration/ais_source.py`, `EventAISAdapter`, 11/11 tests | REAL (MC20 bronze), fails closed to UNAVAILABLE | wired into `RealE2EPipeline`/`GoldenCaseWorkflow` |
| ERA5 | 🟢 | `packages/varuna_source_adapters/forcing_readers.py`, real cube, `sufficient` status | REAL | wired |
| CMEMS | 🟢 | same file, real cube, `sufficient` status (single-timestep risk resolved via `TimeSeriesStatus`) | REAL | wired |
| NETRA v0.2 baseline | 🟢 (engine) / 🟡 (science) | frozen checkpoint, hash-verified, 152-scene official test run once (IoU 0.6458) | REAL model, REAL weights | wired via `NetraDetectionBoundary` |
| NETRA v0.3 domain expansion | 🟠 | training **actively running now**, epoch 4/30, no evaluation yet | REAL (in progress) | not yet integrated (no checkpoint to freeze) |
| PRATIVARTAN / Φ | 🟢 | real ensemble, real forcing, production sensitivity sweep run (500p×20ens×7) | REAL | wired for the cheap path; sensitivity sweep is a separate, tested, **not pipeline-wired** capability |
| NYAYA | 🟢 | real Bayesian attribution, fail-closed proofs (30 tests) | REAL | wired |
| Validity Gate | 🟢 | 9 original + diffusivity + evidence_mode checks, fail-closed, reason codes | REAL logic | wired |
| CHHAYA | 🔴 | see §8 — no real model; `investigate()` in the "inference" class is a hardcoded stub returning `{}` | mock heuristic only | **not called by any canonical case path** |
| PRAVAAH | 🟢 | real current field drift, envelope now propagates (this week's fix) | REAL (cube-backed) / mock available | implemented, **not yet called by `CaseWorkflow`/`GoldenCaseWorkflow`** |
| ABHIYAN | 🟢 | full 5-state gate matrix tested | logic real, tasking content from a mock provider | wired |
| Mission FSM | 🟢 | `varuna_missions`, two-step approval, RBAC-gated approve endpoint noted as a known gap (see §14) | real state machine | wired |
| Alerts | 🟢 | severity/dedupe/materiality/role-routing modules present | real routing logic, real channels disabled | wired |
| Case Engine | 🟢 | reconciled this week, single canonical path documented | mixed real/replay by design | see §10 |
| OperatorCase API | 🟢 | all 8 sections serialize, 19 contract tests + 27 track4-e2e tests | schema real; content depends on upstream stage | wired |
| Frontend | 🟡 | Vite/React scaffold, package still named `temp-app` | mockup-level | **not wired to a running API in this audit** |
| Foundation (event spine/storage) | 🟡 | event spine + repositories real; observability is a 13-line stub; RBAC defined but called from nowhere | real for storage, stub for observability/security | partial |
| Feedback loop (PRAMAN/SMRITI/What-if) | 🟡 | PRAMAN 46 lines, SMRITI 116 lines total, all mock-backed | interfaces real, logic mock | partial |
| Benchmarking | 🟡 | production evaluator infra exists; the older `experiments/go_nogo/` harness is self-documented invalid | mixed | pre-hackathon-grade only |

---

## 5. 🧠 NETRA Status

**Engine implementation status (separate from scientific effectiveness, as required):**

- v0.2 baseline: real trained model, real frozen/hash-verified checkpoint
  (`9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66`), real official 152-scene
  test run **exactly once** at a pre-registered threshold (0.806) — IoU 0.6458, Dice/F1 0.7848,
  PR-AUC 0.8513.
- v0.2 on MC20: **`OOD` / no detection** (max probability 3.05e-6 on real MC20 tiles). This is a
  disclosed, investigated result (`reports/netra_v02/NETRA_POST_BASELINE_SCIENTIFIC_AUDIT.md`),
  primary diagnosis `MIXED_CAUSE` (confirmed domain shift, gated on an unresolved preprocessing
  reconciliation item), not silently reopened or explained away.
- v0.3 domain-expansion pilot: **training right now** (see §2), epoch 4 of 30, losses decreasing,
  no evaluation exists yet. `WHY_RUN2.md` in its own artifact directory documents a genuine,
  transparently-fixed logging bug from a prior attempt (run 1) that would have shown zero
  weak/MIL activity in the record — the experiment itself was unchanged, only its logging cadence.

**Scientific effectiveness:** unresolved. The v0.2 baseline is real and its number on the official
test is real, but it does not generalize to MC20 today, and v0.3's ability to close that gap is
**unknown until this training run completes and is evaluated once, untouched, per the project's
own no-retune-on-test discipline.**

**Do not claim:** "NETRA works on MC20." It does not, as of this audit, and the audit found no
evidence anyone has claimed otherwise in committed reports.

---

## 6. 🌊 PRATIVARTAN / Φ Status

- Real ERA5/CMEMS-backed advection via `CubeBackedCurrentField`/`CubeBackedWindField`, fail-closed
  on insufficient time series or out-of-domain queries.
- Real backward ensemble (`run_backward_ensemble`), honest `n_particles` (measured, not the config
  echo it used to be — fixed this session), honest particle-loss counting.
- Production-scale sensitivity validated as a **standalone, tested capability**: 500 particles ×
  20 ensemble members × 7 perturbation runs against real MC20 forcing
  (`reports/mc20_production_phi_sensitivity.json`). Age/forcing/diffusivity sensitivity are real,
  computed, ADR-ratified numbers; weathering is honestly `None` (no weathering model exists).
- **Gap, disclosed, not fixed in this audit:** the canonical case pipeline
  (`RealE2EPipeline._reconstruct_phi()`) calls the cheap, single-run `build_phi_field()`, which
  always leaves `PhiField.sensitivity = None` — the 7×-cost sweep is not invoked per-case. A real
  MC20 case therefore reaches the Validity Gate's `phi_diagnostics_availability` check as
  **blocking** (`RESTRICTED`), not the sensitivity checks. The sweep is real and validated; it is
  not yet load-bearing in the live pipeline.
- Particle loss on a synthetic-placeholder-seeded run is now fully characterized as a function of
  observation time and seed-cloud width (not a single point estimate) — documented, not fixed
  (there is nothing to fix; it is a property of the placeholder, not a defect).

---

## 7. ⚖️ NYAYA + Validity Status

- NYAYA: real Bayesian attribution, `INSUFFICIENT_COVERAGE` as a first-class outcome (not an
  error), spatial-vs-temporal AIS evidence never conflated (`test_spatial_candidacy_is_never_
  promoted_to_temporal_evidence`).
- Validity Gate: 11 checks (was 9; `phi_diagnostics_availability` and `evidence_mode` added
  previously, `diffusivity_sensitivity` added this week). Fail-closed proven both directions for
  every check (`tests/unit/test_validity_gate.py`, 17 tests).
- **Scientific conclusion vs execution status vs EvidenceMode are three separate, unflattened
  vocabularies** — verified directly in code (`StageStatus` / `ValidityState` / `EvidenceMode`, three
  distinct enums in `varuna_integration.stage` and `varuna_contracts.evidence`), and explicitly
  documented as a deliberate decision in `CASE_ORCHESTRATION_RECONCILIATION.md` §4 after a real
  proposal to collapse them was considered and rejected this week.

---

## 8. 🌫 CHHAYA Status — **the honest finding**

**CHHAYA is interface-only with a mock heuristic. There is no trustworthy latent-source engine.**

Verified directly, not inferred from the architecture diagram:

- `ChhayaProvider` (the real ABC) declares `investigate(scene_path, ais_positions, scene_bbox,
  envelope) -> (List[DarkVesselDetection], LatentFinding)`.
- `MockChhayaProvider.investigate()` **does** implement this correctly — a real, deterministic,
  AIS-coverage-based heuristic (dark-vessel-vs-AIS-proximity logic), not a trained model. This is a
  legitimate mock, clearly not claiming to be ML.
- `ChhayaInferenceService` (the class named for real model inference, backed by `ModelLoader`) is
  **broken relative to its own contract**: its `investigate(slick_id, context)` method has a
  completely different signature than the ABC requires and unconditionally `return {}` — it has
  never been implemented. Separately, it defines a `forecast()` method that is not even part of
  `ChhayaProvider` at all (that method belongs to `PravaahProvider`) — this looks like leftover/
  cross-wired scaffolding, not a working real-inference path.
- **No canonical case-orchestration path calls CHHAYA at all** — confirmed by grep across
  `CaseWorkflow`, `golden_case_engine.py`, and `varuna_integration/*.py`: zero references. The only
  callers are `WhatIfSimulator` (via the broken `forecast()`) and a stale end-to-end test
  (`tests/e2e/test_m4_full_pipeline.py`) that the project's own plan documents already flagged as
  misleading (it stubs PRATIVARTAN/NYAYA/the gate).

**Status: 🔴 NOT STARTED (real model) / interface + mock only.** Do not present CHHAYA as
implemented in a demo beyond "the interface and a coverage heuristic exist."

---

## 9. 🌊 PRAVAAH Status

- `CubeBackedPravaahProvider`: real forward drift on a real current field, fail-closed
  (out-of-domain mid-trajectory freezes rather than extrapolates), landfall detection via
  `check_landfall`.
- `MockPravaahProvider`: fabricated fixed-drift model, now (this week) unconditionally marked
  `SIMULATED` regardless of caller input — closes a real gap where it could previously have
  inherited a `REAL` claim from a caller's envelope.
- `ForwardForecast` now (this week, ADR-0009) carries `evidence_mode`/`provenance`/`case_id` —
  previously silently dropped despite the provider protocol already receiving an envelope.
- **Gap:** not yet invoked by `CaseWorkflow` or `GoldenCaseWorkflow`'s default run — implemented
  and unit-tested in isolation, not yet load-bearing in the live per-case pipeline (the same shape
  of gap as PRATIVARTAN's sensitivity sweep, §6).

**Status: 🟢 implementation-ready, 🟠 integration required.**

---

## 10. 🧩 Case Engine Status

**One canonical orchestration path exists, and this audit verified — not assumed — that claim.**

- `varuna_domain.CaseWorkflow`: 10 direct callers found (`grep -c "CaseWorkflow("` across
  `apps/`/`tests/`/`scripts/`) — still live, still used by older tests and the API's case router,
  but documented (by the reconciliation work, and independently confirmed by reading
  `case_workflow.py`) as the synthetic-forcing path.
- `GoldenCaseWorkflow` (`packages/varuna_domain/golden_case_engine.py`, 567 lines): the reconciled,
  now-canonical path — an adapter over `CaseWorkflow`'s persistence and `RealE2EPipeline`'s real
  producer stages, adding case lifecycle, idempotency (`(case_id, config_hash)` cache keying,
  verified in the report's own commands), and a `deterministic_run_id` this reconciliation added.
  3 test files reference it (`test_golden_case_engine.py`, `test_golden_case_engine_mc20_e2e.py`,
  `test_replay_fixtures.py`).
- The reconciliation is **social, not enforced** — `CaseWorkflow` was not deleted or blocked from
  new callers (per the project's no-delete convention), so a future contributor could still wire a
  new call site to the older path by mistake. This is a real, named residual risk, not a solved one.
- Deterministic `run_id` (`deterministic_run_id()`, SHA-256 over case/mode/config/model/dataset) now
  coexists with the older wall-clock `run_id` — two identities for two different questions
  (reproducibility vs. execution-instance correlation), not a redundancy.

---

## 11. 🎯 ABHIYAN Status

- `AbhiyanService.plan_mission()`: real, tested, binary-correct gate — `VALID`/`DEGRADED` permit
  tasking generation; `RESTRICTED`/`INCONCLUSIVE`/`gate_state=None` produce zero taskings, never an
  exception, never partial dispatch (`test_abhiyan_full_gate_state_matrix`, added this week,
  5 explicit states).
- Tasking **content** (which asset, which search box) comes from `MockAbhiyanProvider` — a
  reasonable placeholder, not a real assignment optimizer (no cost/risk/urgency scoring engine
  exists behind it; the "decision value/cost/risk/urgency" language in the target architecture is
  not yet backed by real optimization logic).

**Status: 🟢 gate logic real and safe · 🟡 tasking content is a placeholder, not an optimizer.**

---

## 12. 🚢 Mission / Alerts Status

- Mission FSM: real state machine (`varuna_missions`), the `AVAILABLE → ASSIGNED` two-step human
  approval requirement is enforced structurally (per `GOLDEN_CASE_ENGINE_REPORT.md`'s own
  limitations note — `GoldenCaseWorkflow` never auto-calls `approve_and_assign()`).
- A previously-known gap — `approved_by` unvalidated, no RBAC check, no `POST /v1/missions/{id}/
  approve` endpoint — is **partially addressed**: `apps/api/routers/missions.py` exists, but RBAC's
  `has_permission()` is still called from nowhere in the whole repository (verified by grep) — the
  approval endpoint, if present, is not RBAC-gated today.
- Alerts: severity/dedupe/materiality/role-routing modules all present and non-trivial (36/19/23/14
  lines respectively, not stubs); real channels (SMTP/Twilio/CAP-XML) remain disabled by design.

**Status: 🟢 lifecycle correct and tested · 🟡 authorization/RBAC not enforced end-to-end.**

---

## 13. 🖥 Operator Dashboard Status

`GET /v1/cases/{case_id}/operator-view` serializes all 8 required sections (origin, ais,
attribution, validity, forecast, decision [= recommendation], mission, alerts) — verified against
a **real MC20 run artifact**, not a synthetic fixture (`reports/mc20_track4_operator_case.json`).
That artifact is the fail-closed case (NETRA found nothing), so it proves the schema holds when
producers legitimately return nothing — not that a populated case renders end to end (a distinct,
not-yet-independently-re-verified claim; see the qualifier this audit's predecessor task already
added to `reports/track2/TRACK_2_FINAL_REPORT.md`).

`OperatorCase.provenance` (top-level rollup) was found empty for Track-4-pipeline-produced cases as
recently as this week and has since been fixed (`case_bridge.py` now feeds
`model_versions`/`source_ids` from what each stage reports) — verified fixed via 46 passing tests
across `test_operator_case.py` + `test_track4_mc20_e2e.py`.

**Status: 🟢 schema and fail-closed behavior real and tested · 🟡 populated-content path not
independently re-verified in this audit (schema exists ≠ every field independently confirmed
correct on a populated case).**

---

## 14. 🔐 Foundation / Security / Provenance

| Layer | Status | Evidence |
|---|---|---|
| Event Spine | 🟢 prototype-ready | `packages/varuna_pravaah/event_spine.py`, reused unchanged by Golden Case Engine |
| Data/Object Storage | 🟢 prototype-ready | `varuna_infra/minio_store.py` + `inmemory_store.py`, `CaseRepository`/`ArtifactRepository` real |
| Compute Layer | 🟡 partial | Celery exists (`apps/worker/celery_app.py`, `varuna_infra/celery_runner.py`) — not verified running in this audit (no listener on the broker port) |
| ML/Model Layer | 🟢 prototype-ready | `ModelLoader`, `NetraDetectionBoundary`, checkpoint hash verification all real |
| Observability | 🔴 stub | `packages/varuna_infra/observability.py` is 13 lines — no structured logging, no correlation-id threading verified |
| Security / RBAC | 🔴 defined but unused | `has_permission()` (`varuna_infra/rbac.py`) has **zero call sites** anywhere in the repo (verified by grep) |
| Auth | 🟡 partial | `auth.py`/`auth_models.py` exist; not verified wired to a running API in this audit (no live process) |

---

## 15. 🧪 Tests / Verification

**Do not read this as "the whole repository is green."** Four suites were actually executed this
audit; others were not re-run and are reported from their last known state.

| Suite | Result (this audit, fresh run) |
|---|---|
| `tests/unit` + `tests/contract` + `tests/integration` + `tests/e2e` | **576 passed, 10 skipped, 1 failed** (342s) |
| `tests/api` + `tests/regression` + `tests/scientific` + `tests/robustness` | **25 passed, 3 failed** |

**The one `unit/contract/integration/e2e` failure:**
`tests/unit/test_netra_training.py::test_netra_training_loop` — `TypeError: 'NetraSample' object is
not subscriptable` (`packages/varuna_netra/training/trainer.py:250`). NETRA-owned, pre-existing,
reproduces identically to the baseline observed before this week's Track 2 work — **not** touched,
per the absolute rule against modifying NETRA training code.

**The three `scientific` failures:** `tests/scientific/test_go_nogo_fair_harness.py` — all three
fail with `ValidationError: 1 validation error for EvidenceEnvelope / mode / Field required`,
inside `experiments/go_nogo/prativartan.py`. This is the **already-self-documented-invalid**
`experiments/go_nogo/` harness (see `EVALUATION.md`'s own opening line: "The harness is currently
invalid — read this first") — it predates `EvidenceMode` being made a required field (ADR-0006) and
was never updated to match. Classification: **PRE_EXISTING / EXPECTED_SCIENTIFIC_BLOCK**, not a
regression from this week's work.

**Not re-run this audit** (reported from the most recent known state, cited by source):
- Full `tests/` sweep including every marker combination — not exhaustively re-run; the four
  directories above cover unit/contract/integration/e2e/api/regression/scientific/robustness, which
  is the meaningful superset for this report's purpose.
- Frontend tests — no test script found in `apps/web/package.json` beyond lint/build; no frontend
  test suite exists to run.

---

## 16. 🔗 End-to-End Integration Status

| Path | Status |
|---|---|
| Real forcing (ERA5+CMEMS) → PRATIVARTAN → PhiField | ✅ real, tested |
| PhiField → NYAYA → Validity | ✅ real, tested, fail-closed both directions |
| Validity → ABHIYAN → (no) Mission | ✅ real, tested (5-state matrix) |
| Real current field → PRAVAAH | 🟢 implemented, 🟠 not called by the case pipeline |
| Real AIS → canonical join → NYAYA | ✅ real, tested, canonical MC20 numbers reproduced |
| NETRA detection → downstream chain | ✅ real MC20 run demonstrates correct `NO_SLICK_DETECTED` → `not_yet_produced` propagation through every stage, not faked |
| Case → OperatorCase → (dashboard) | 🟢 API real and tested; 🔴 no frontend currently consumes it live |
| CHHAYA → anything | 🔴 not integrated into any canonical path |

---

## 17. 📈 Completion Estimates

**AUDIT-BASED ESTIMATE — not a measured scientific fact.** Weighted by rough engineering surface
area and criticality, scored against evidence gathered in this audit.

| Component | Score | Confidence | Basis |
|---|---:|---|---|
| Data / ingestion | 90 | HIGH | 3/4 real modalities validated against real SAFE/ERA5/CMEMS |
| Trust / provenance | 70 | MEDIUM | envelope propagation real; top-level rollup gap found+fixed this week; RBAC unused |
| NETRA | 55 | MEDIUM | real baseline + real number, but MC20-null and v0.3 mid-training/unevaluated |
| PRATIVARTAN | 80 | HIGH | real, tested, production-scale validated, but sensitivity sweep not pipeline-wired |
| NYAYA | 85 | HIGH | real, fail-closed, well-tested |
| CHHAYA | 15 | HIGH | interface + mock only, no real model, not integrated |
| PRAVAAH | 65 | MEDIUM | real logic, not wired into the case pipeline |
| Validity Gate | 90 | HIGH | real, comprehensive, actively extended this week |
| Case Engine | 75 | HIGH | reconciled this week, one documented canonical path, residual risk of a stray new caller |
| ABHIYAN | 60 | MEDIUM | gate logic real; tasking content is a placeholder |
| Mission | 65 | MEDIUM | real FSM; RBAC/approval gate incomplete |
| Alerts | 60 | MEDIUM | real routing logic; channels disabled by design |
| OperatorCase | 75 | HIGH | schema real and tested against a real run; content-completeness not independently re-verified |
| Frontend | 20 | HIGH | scaffold only, unnamed template project, no map/routing/state libs, not wired to a live API |
| Foundation | 45 | MEDIUM | storage/event-spine real; observability/RBAC are stubs |
| Feedback loop | 30 | MEDIUM | interfaces exist, logic is mock throughout |
| Benchmarking | 40 | MEDIUM | production evaluator infra exists; older harness self-documented invalid |

**Overall engineering completeness: ~62%** (AUDIT-BASED ESTIMATE)
**Hackathon prototype completeness: ~66%** (AUDIT-BASED ESTIMATE — weighted toward what a demo needs: backend chain + case engine + validity, less toward frontend/benchmarking)
**Research completeness: ~35%** (AUDIT-BASED ESTIMATE — NETRA MC20 gap unresolved, sensitivity/PRAVAAH not pipeline-wired, go/no-go harness invalid, CHHAYA absent)

```
DATA / INGESTION      █████████░  90%
NETRA                 █████░░░░░  55%
PRATIVARTAN           ████████░░  80%
NYAYA                 ████████░░  85%
CHHAYA                █░░░░░░░░░  15%
PRAVAAH               ██████░░░░  65%
VALIDITY GATE         █████████░  90%
CASE ENGINE           ███████░░░  75%
ABHIYAN               ██████░░░░  60%
MISSION / ALERTS      ██████░░░░  62%
OPERATORCASE          ███████░░░  75%
FRONTEND              ██░░░░░░░░  20%
FOUNDATION            ████░░░░░░  45%
FEEDBACK LOOP         ███░░░░░░░  30%
BENCHMARKING          ████░░░░░░  40%

Hackathon Prototype:   ██████░░░░  66%
Research/Benchmarking: ███░░░░░░░  35%
```
*(Audit-based engineering estimate — not a measured scientific fact.)*

---

## 18. 🧭 Critical Path to Hackathon

```
CURRENT (backend logic real, nothing running)
   ↓
MUST DO: start apps/api + a frontend page that calls GET /v1/cases/{id}/operator-view
   ↓
MUST DO: run GoldenCaseWorkflow.run_replay_case() against one of the 6 REPLAY fixtures to get a populated (not fail-closed-empty) OperatorCase to show
   ↓
SHOULD DO: wire PRAVAAH into the replay/real run so "forecast" is not empty in the demo
   ↓
SHOULD DO: label CHHAYA explicitly as "not in this demo" rather than silently omit it
   ↓
DO LATER: RBAC on mission approval, observability, real alert channels, frontend real map/state libraries
   ↓
HACKATHON DEMO READY
```

**MUST DO:** get *something* running and clickable; use a REPLAY fixture for a populated case
(the only real-MC20 artifact on disk today is the fail-closed empty one).
**SHOULD DO:** PRAVAAH wiring, explicit CHHAYA disclosure in the talk track.
**DO LATER:** RBAC, observability, real alert channels, frontend maturity, benchmarking harness fix.

---

## 19. 🔥 Top 10 Remaining Items

| # | Task | Module | Why it matters | Dependency | Est. time | Risk | Blocks demo? |
|---|---|---|---|---|---|---|---|
| 1 | Start API + point a minimal frontend page at `operator-view` | `apps/api`, `apps/web` | Nothing is currently running to show | none | 2–6h | Low | **Yes** |
| 2 | Run one populated REPLAY case end to end and screenshot/record it | `golden_case_engine.run_replay_case` | Only fail-closed-empty real artifact exists today | #1 | <2h | Low | **Yes** |
| 3 | Wire PRAVAAH into the canonical pipeline's forecast stage | `varuna_integration.pipeline` | "Forecast" is currently always empty in real/replay runs | none | 6–12h | Medium | Should |
| 4 | Wire the Φ sensitivity sweep into the canonical pipeline (or explicitly gate/label it) | `varuna_integration.pipeline`, `phi_builder.py` | Validity Gate currently blocks on `phi_diagnostics_availability` for every real case | PRATIVARTAN sweep already exists | 6–12h | Medium | Should |
| 5 | Give CHHAYA a real (even simple, e.g. classical CFAR-style) dark-vessel detector, or formally deprecate it from the demo | `varuna_chhaya` | Currently the weakest, most misleading-if-shown component | none | >3 days for real; <2h to formally disclose | Low (disclosure) / High (real impl) | No (if disclosed) |
| 6 | RBAC-gate mission approval | `varuna_infra/rbac.py`, `apps/api/routers/missions.py` | Currently anyone/nothing enforces who approves a mission | none | 2–6h | Low | No |
| 7 | Wait for and evaluate v0.3 pilot (currently training) | `varuna_netra` | Determines whether MC20 domain gap closes | GPU (currently busy) | untouchable now; hours once done | High (scientific, not engineering) | No (but high-value if positive) |
| 8 | Replace/retire `experiments/go_nogo/` or fix its `EvidenceEnvelope` construction | `experiments/go_nogo/prativartan.py` | 3 test failures, self-documented-invalid harness still in the tree | none | 2–6h to fix construction; already documented as invalid scientifically | Low | No |
| 9 | Fill `apps/web/package.json` name/branding and add a real routing/state/map stack | `apps/web` | Currently a default Vite template (`"name": "temp-app"`) | none | 6–12h for a minimally real cockpit | Low | Should |
| 10 | Flesh out `observability.py` beyond 13 lines (correlation-id threading, structured logs) | `varuna_infra/observability.py` | No operational visibility into a running demo | none | 2–6h | Low | No |

---

## 20. ⚠️ Risks / Known Limitations

- **NETRA's MC20 result is a real null.** Any demo must not imply NETRA "found" anything on MC20 —
  it did not, and this is documented as an open scientific question (`MIXED_CAUSE`), not resolved.
- **Two case-orchestration surfaces exist.** Reconciled this week, but nothing *prevents* a future
  contributor from wiring a new caller to the older, synthetic-forcing `CaseWorkflow` path by
  mistake — this is a social convention, not an enforced one.
- **CHHAYA has no real model.** Presenting it as functional would misrepresent the system.
- **PRAVAAH and the Φ sensitivity sweep are both real but not pipeline-wired** — a real MC20 case
  today reaches `RESTRICTED` at the Validity Gate specifically because sensitivity diagnostics are
  unavailable in the live path, not because the science is missing.
- **No live process is running except NETRA training.** A demo requires deliberately starting the
  stack; this has not been verified end-to-end with all services up in this audit.
- **RBAC is entirely unenforced.** `has_permission()` has zero callers.
- **The frontend is a scaffold**, not a cockpit — no map library, no routing, default template name.
- **`experiments/go_nogo/` is scientifically invalid by its own documentation** and additionally
  now fails to even construct (contract drift) — it must not be cited as evidence of attribution
  accuracy in any presentation.

---

## 21. 🎤 What We Can Demonstrate Today

| Capability | Status |
|---|---|
| 1. Create/open a case | DEMONSTRABLE WITH REPLAY (`GoldenCaseWorkflow.run_replay_case`, 6 fixtures) |
| 2. Ingest real/replay data | DEMONSTRABLE NOW for real ERA5/CMEMS/AIS (scripted); DEMONSTRABLE WITH REPLAY for a full case |
| 3. Detect/represent detection | DEMONSTRABLE WITH REPLAY (real path exists but currently nulls on MC20) |
| 4. Reconstruct origin | DEMONSTRABLE WITH REPLAY / DEMONSTRABLE NOW as a standalone script against real forcing |
| 5. Attribute vessels | DEMONSTRABLE WITH REPLAY / real AIS join DEMONSTRABLE NOW as a standalone script |
| 6. Apply validity gate | DEMONSTRABLE NOW (script-level) and WITH REPLAY (full case) |
| 7. Forecast impact | PARTIAL — PRAVAAH works standalone, not wired into the case run |
| 8. Produce recommendation | DEMONSTRABLE WITH REPLAY (ABHIYAN gate matrix is real) |
| 9. Create mission | DEMONSTRABLE WITH REPLAY (two-step approval enforced) |
| 10. Generate alerts | DEMONSTRABLE WITH REPLAY (routing logic real, channels disabled) |
| 11. Show everything in dashboard | PARTIAL — API is real; no frontend currently renders it live |
| 12. Show provenance/evidence state | DEMONSTRABLE WITH REPLAY (OperatorCase provenance rollup, fixed this week) |
| 13. Handle OOD/unavailable safely | DEMONSTRABLE NOW — the real MC20 run is the actual evidence for this, not a contrived example |

**Suggested honest demo storyline (5–10 min):**

```
Open a REPLAY case (CASE-VALID fixture, clearly labelled SIMULATED)
  ↓
Show Observation → Detection (a plausible, labelled-synthetic slick)
  ↓
Show Origin reconstruction against forcing (mention: real forcing code path exists;
  this fixture demonstrates the mechanism)
  ↓
Show AIS candidates (pivot here to the REAL MC20 AIS join as a second, real-data beat —
  "this part is not a fixture")
  ↓
Show Validity Gate verdict with reason codes, including a deliberately RESTRICTED example
  ↓
Show ABHIYAN recommendation / no-recommendation depending on gate state
  ↓
Show Mission creation, two-step approval
  ↓
Show Alerts, explicitly noting channels are disabled by design
  ↓
Close on the REAL MC20 run: NETRA found nothing, and show the WHOLE chain
  correctly reporting "not yet produced" with real reasons — this is the
  fail-closed story, and it is the most scientifically honest thing in the demo.
```

No fictional REAL outputs are used in this storyline. The only simulated segment (the fixture case)
is explicitly labelled as such at every step it appears.

---

## 22. 🚀 Recommended Next 24 Hours

1. Start the full stack once (`make up-infra`, API, frontend) and verify the operator-view endpoint
   renders in a browser against a REPLAY case — currently unverified live.
2. Wire PRAVAAH into the canonical pipeline's forecast stage so "impact forecast" is not
   structurally empty in every run.
3. Prepare the demo talk track's explicit disclosure list (CHHAYA absent, RBAC unenforced, real
   alert channels disabled, NETRA MC20 result is a real null) so nothing is misrepresented under
   time pressure.

---

## 23. Final Verdict

**DEMOABLE_WITH_REPLAY**

The system has substantially more real, tested engineering behind it than a typical hackathon
prototype — real SAR/ERA5/CMEMS/AIS data, a real trained NETRA baseline with a real (if currently
null-on-MC20) result, real PRATIVARTAN/NYAYA/Validity logic with extensive fail-closed testing, and
a genuinely reconciled single canonical case-orchestration path. It is not yet
`HACKATHON_PROTOTYPE_READY` on its own terms because: nothing is currently running end to end, the
only real-MC20 case artifact on disk is the (correct, but not visually rich) fail-closed-empty one,
CHHAYA has no real model, and the frontend is a scaffold rather than a cockpit. `PRODUCTION READY`
is not used and would not be honest for any part of this system.

---

## Audit Safety

```
files modified: 0
files created: 1 (this report, reports/project/VARUNA_FINAL_PROJECT_STATUS.md)
files deleted: 0
files moved: 0
files renamed: 0
overwritten: 0
NETRA training process: observed only, not touched, not interrupted
```
