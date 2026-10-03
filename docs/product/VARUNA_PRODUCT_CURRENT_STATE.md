# VARUNA GRID v2 — Product Current State (Phase 0 Reconnaissance)

**Branch:** `feat/netra-real-training` @ `650b0b8`
**Date:** 2026-09-02
**Method:** direct inspection of `packages/` + `apps/`. Nothing here is carried
over from a previous session's report unless independently re-verified; where a
prior document is cited it is because this session read the code it describes.

`packages/` + `apps/` are canonical. The legacy `src/` tree (13 mirrored
subpackages) was confirmed present and is excluded from every finding below.

---

## 1. The headline finding

**The live HTTP API does not use `GoldenCaseWorkflow`.**

Searching `packages/` + `apps/` for `GoldenCaseWorkflow` returns hits in exactly
three places: its own definition (`packages/varuna_domain/golden_case_engine.py`),
one docstring reference in `varuna_integration/intelligence.py`, and two test
files. **No `apps/` file imports it.**

Meanwhile every case-facing API route is built on the legacy orchestrator:

| Site | Import |
|---|---|
| `apps/api/dependencies.py:9,77,78` | `from varuna_domain.case_workflow import CaseWorkflow` |
| `apps/api/routers/cases.py:7` | same — all 10 endpoints take `CaseWorkflow = Depends(get_workflow)` |
| `apps/api/routers/events.py:7` | same |
| `apps/api/operator_case_view.py:35` | same |

This is the "duplicate production pipeline" condition in the readiness
checklist, and it is currently the *only* pipeline reachable over HTTP.

It is not merely a naming issue. `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md`
§5 records that `CaseWorkflow.reconstruct()` calls `reconstruct_origin()` with no
`current`/`wind`/`input_envelope`, so **the API's science path runs synthetic
forcing under a SIMULATED envelope**, while `GoldenCaseWorkflow`'s REAL path runs
real ERA5/CMEMS. Two case-shaped entry points with different forcing realism
coexist, and the one exposed to an operator is the weaker one.

Nothing is *mislabelled* — the SIMULATED envelope is honest — but a frontend
built against today's API would show simulated science behind real-looking
chrome.

**Consequence for execution order:** Phase 6 (canonical workflow enforcement) is
not a tidy-up at position six. It is a prerequisite for Phases 9 and 10, because
an API contract and an operator console built on `CaseWorkflow` would harden the
wrong pipeline.

---

## 2. Working features (verified this session)

| Capability | Where | Evidence |
|---|---|---|
| Canonical case engine | `varuna_domain/golden_case_engine.py` (567 ln) | `run_case()` / `run_replay_case()`; idempotency keyed `(case_id, config_hash)`; `deterministic_run_id()` |
| 10-stage real pipeline | `varuna_integration/pipeline.py` | forcing → ais → netra → phi → attribution → validity → forecast → decision → mission → alerts |
| Frozen-checkpoint gate | `varuna_integration/netra_boundary.py` (601 ln) | `check_checkpoint_frozen()` verifies sha256 against `.frozen.json`; refuses on mismatch |
| Evidence Ledger | `varuna_evidence/ledger.py` | append/revise/retract, support + contradiction links, `lineage()`, `audit_trail()`, `worst_mode()` |
| CHHAYA v0.1 | `varuna_chhaya/hypothesis_engine.py` | declared-likelihood-ratio Bayesian update; absence-contributes-nothing enforced via `X \| None` params |
| SMRITI v0.1 | `varuna_smriti/memory.py` | `store_case`, `update_case`, `retrieve_similar_cases`, `retrieve_failure_patterns`, `retrieve_prior_outcomes`, `corridor_case_count`, `SimilarityBreakdown` |
| Agentic loop | `varuna_agentic/loop.py` | deterministic OBSERVE→…→STOP with fail-closed guard |
| Authorization primitives | `varuna_infra/authorization.py` (134 ln) | `Principal`, `authorize()` (raises, not bool), `AuditLog` |
| JWT primitives | `varuna_infra/auth.py` (32 ln) | real `create_access_token` / `verify_token`, HS256 |
| Adapter boundary | `varuna_source_adapters/protocol.py` | `fetch_with_mode()` — the single place `is_simulated` becomes `EvidenceMode`; UNAVAILABLE on raise or failed health check |
| Frozen NETRA v0.2 | `artifacts/checkpoints/netra_v0_2/…_best.pt` | sha256 `9f38c690…`, `best_f1_threshold=0.806`, `scientific_status: EXPERIMENTAL / UNVALIDATED` |

---

## 3. Gaps, by phase, with evidence

### Phase 4A — NETRA detection evidence

`netra_boundary.detect_tiles()` already emits `decision_threshold`,
`max_probability`, `n_tiles`, `model_version`, `scientific_status`. What it
**discards** is the raw logits tensor — `FrozenCheckpointNetraProvider.detect()`
computes `probs = softmax(logits)` at line 236 and lets `logits` fall out of
scope. That tensor is exactly the input an energy-based OOD score needs, so 4A
and 4B are one change, not two.

### Phase 4B — OOD is a threshold-ratio heuristic

`intelligence.assess_ood_from_detection()` classifies on
`max_prob < threshold * 0.01` → OUT_OF_DOMAIN, `< threshold` → BORDERLINE, else
IN_DOMAIN. Every branch's rationale string already self-labels
`"HEURISTIC, not a calibrated OOD score."` — honest, but it is a re-reading of
the decision threshold, not an independent domain signal.

**Available raw material for a real no-training signal:** `data/gold/netra_v0_2/val`
holds 3,616 in-domain image tiles (7,232 files, img+mask pairs). An energy score
`E(x) = -logsumexp(logits)` against a fixed reference percentile set derived from
those tiles is deterministic, needs no training, and does not touch the
checkpoint.

### Phase 4C — preprocessing compatibility is unverified

Named in `CASE_ORCHESTRATION_RECONCILIATION.md` §8 as *"the single most
consequential gap this reconciliation surfaced without closing"*, and confirmed
in code: `NetraModelSpec` has no `preprocessing_version` field, and
`golden_case_engine.detector_provider_info()` reports a constant
`ASSUMED_NETRA_PREPROCESSING_VERSION = "netra-norm-v0.2-nodata-excluded"` —
explicitly labelled ASSUMED, never measured.

This is the highest-priority item in the session. A checkpoint fed differently
normalized tiles detects nothing, and **today nothing distinguishes that from the
genuine MC20 domain gap** — the two competing explanations for Demo A's null
result are currently indistinguishable.

### Phase 2 — CHHAYA inputs

The engine already accepts `elongation`, `area_km2`, `distance_to_shore_km`,
`wind_speed_ms`, `phi_available`, `phi_converged`, `prior_cases_same_corridor`.
The **call site** (`intelligence.py:397-406`) passes only four: `detection_present`,
`nearest_vessel_km`, `nearest_vessel_temporally_matched`, `n_ais_tracks`. Phase 2
is a wiring job on the caller, not an engine change.

**Live defect found:** `intelligence.py:387-389` computes
`corridor = self.smriti.corridor_case_count(...)` and then never passes it —
`prior_cases_same_corridor` stays at its default `0`. A SMRITI query runs on every
case and its result is discarded.

**Fabrication risk to avoid:** `varuna_source_adapters/static_gis.py` is a 5-line
stub whose `check_distance_to_coast()` returns a hardcoded `10.0`. That value must
not be wired into `distance_to_shore_km` — 10.0 km sits inside CHHAYA's
`COASTAL_PROXIMITY_KM = 15.0` boundary, so wiring it would give **every case**
fabricated coastal-proximity support.

### Phase 5 — authorization

`apps/api/middleware/auth.py` is a **no-op**: `dispatch()` calls `call_next` and
returns, under the comment `# Stub for Auth`. Real JWT verification exists in
`varuna_infra/auth.py` and is imported by nothing in `apps/`. Only mission
approval is enforced, via the `principal` argument threaded through
`varuna_missions.service.approve_and_assign()`.

### Phase 7 — observability

`packages/varuna_infra/observability.py` is 13 lines. Both
`MetricsTracker.record_inference_time` and `.increment_error_count` are literally
`pass # Stub`. This is a build, not a hardening.

### Phase 8 — live data

`era5.py` (71 ln), `copernicus_marine.py` (63 ln) and `ais.py` (54 ln) are
implemented against the `SourceAdapter` ABC. Two are not:

- `sentinel1.py` (5 ln) returns `{"id": scene_id, "data": "mock_s1_data"}` and
  does not subclass `SourceAdapter`.
- `static_gis.py` (5 ln) — the hardcoded coast distance described above.

There is no orchestration layer above the adapters: no request planner, retry,
timeout, or cache-keyed case association.

### Phase 9 / 10 — API and frontend

API surface is thin: `cases.py` 170 ln, `missions.py` 74, `readiness.py` 33,
`events.py` 32, `dashboard.py` 22, `alerts.py` 10, `prahari.py` 14. Of the fifteen
operator endpoints the target contract names, roughly six exist.

`apps/web/src/App.tsx` is **241 lines, single file**, with no component tree,
router, or generated API types. None of the six named operator views exist.
Phase 10 is a frontend build.

---

## 4. Dependency order (what actually blocks what)

```
Phase 4C  preprocessing contract ─┐
                                  ├─→ 4B real OOD ──→ 4A evidence completeness
Phase 6   canonical workflow ─────┴─→ 9 API ──→ 10 frontend ──→ 14 UX
Phase 7   observability ──────────→ 4 agentic-loop observability
Phase 5   authorization ──────────→ 9 API (auth on state-changing routes)
Phase 2   CHHAYA wiring ←── needs real wind (forcing stage) + real shore distance
Phase 12  benchmark ←── needs 4B, 2, 6 settled, or it bakes in current behaviour
```

Two edges are worth stating explicitly:

- **4C precedes 4B.** Calibrating a domain signal on top of a possibly-wrong
  preprocessing path produces a confidently wrong reference distribution.
- **6 precedes 9 and 10.** An operator API and console built against
  `CaseWorkflow` would harden the non-canonical pipeline.

---

## 5. Risks

| Risk | Severity | Note |
|---|---|---|
| Preprocessing mismatch invalidates the MC20 null result | **High** | Changes the scientific meaning of Demo A, not just its plumbing |
| Migrating the API off `CaseWorkflow` breaks existing consumers | **High** | `operator_case_view.py` (459 ln) is typed against `CaseWorkflow`; peer sessions have been active in that file |
| Wiring `static_gis` / `sentinel1` stubs propagates fabricated values | **High** | Both return constants, and both are precisely the inputs Phases 2 and 8 want |
| Phase 10 scope | **Medium** | Six views from a 241-line single file is a build, not an integration |
| Phase 12 ground truth | **Medium** | Most scenario families have no known outcome; those test self-consistency, not correctness, and must be labelled so |
| Shared worktree | **Medium** | Branch carries 15 modified + many untracked NETRA-owned files. Stage only own files; never `git add -A` |

---

## 6. Frozen assets — untouched, verified by inspection only

- `artifacts/checkpoints/netra_v0_2/netra_baseline_v02_dac482fcd84a_best.pt` —
  sha256 `9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66`
- `data/gold/netra_v0_2/` — NETRA-GOLD-v0.2, read-only reference source for the
  OOD distribution
- `data/gold/events/mc20_v0_1/` — MC20 event gold
- GPU idle at recon time (8% util, 1.4 GB / 12 GB); no NETRA training process
  running

---

*Phase 0 complete. This document records what was found, not what was fixed.*
