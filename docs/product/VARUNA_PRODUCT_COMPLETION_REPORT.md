# VARUNA GRID v2 — Product Completion Report

**Session:** VARUNA_PRODUCT_READY hardening
**Date:** 2026-09-02
**Branch:** `feat/netra-real-training` @ `650b0b8` (shared worktree; NETRA
training files untouched throughout — verified by `git status` scoping)

## Final status: **VARUNA_PRODUCT_REQUIRES_FIX**

Not `VARUNA_PRODUCT_READY`. Six of sixteen phases were completed to a
verified, tested standard; the remainder — most consequentially the frontend,
the live-data orchestration layer, and the benchmark — were not attempted, and
saying otherwise would be exactly the kind of unearned confidence this session
was asked to avoid. What follows is the honest breakdown, not a partial
credit tally dressed up as a pass.

---

## 1. What BUILT means here vs. VERIFIED vs. REUSED

- **BUILT** — new code, new tests, this session.
- **VERIFIED** — existing code, confirmed correct by direct inspection or a
  new diagnostic this session; not modified.
- **REUSED** — existing code, called from new code without modification.
- **PARTIALLY BUILT** — some of a phase's scope done, rest explicitly not.
- **BLOCKED** — a real dependency (credentials, a stop condition, another
  session's active file) prevents proceeding.
- **FUTURE** — in scope by the prompt, not attempted, named as such.

---

## 2. Phase-by-phase account

### Phase 0 — Reconnaissance: **BUILT**
`docs/product/VARUNA_PRODUCT_CURRENT_STATE.md`. Headline finding: the live API
does not use `GoldenCaseWorkflow` (§1 of that doc) — this reshaped the
execution order for every phase after it.

### Phase 1A — NETRA evidence verification: **VERIFIED, then BUILT (energy field)**
`decision_threshold`, `max_probability`, provenance were already populated.
Added `min_energy` alongside them (new field on `StageResult.detail`,
additive, does not change any existing field's meaning).

### Phase 1B — Real OOD signal: **BUILT**
`packages/varuna_integration/ood_energy.py` (new), energy-score reference
(`scripts/build_ood_energy_reference.py`, 200 deterministically-sampled Gold
v0.2 val tiles, seed=42, no training). Combined with the pre-existing
class-probability heuristic in `combine_ood_signals()`, which reports
disagreement explicitly rather than picking a winner. Verified against MC20:
the two signals disagree (probability says out-of-domain, energy says
in-domain-typical), now reported as BORDERLINE with both readings stated —
previously reported as a confident OUT_OF_DOMAIN from the probability signal
alone. Demo A was re-run and its report regenerated to reflect this; no
frozen asset was touched to produce it.

### Phase 1C — Preprocessing compatibility: **VERIFIED**
`docs/adr/ADR-0011-preprocessing-compatibility-verified.md`. Normalization
statistics confirmed correct (exact Gold v0.2 clip stats, applied verbatim).
The documented channel-binding fix (`resolve_frozen_v0_2_channel_binding`) was
found to have zero callers — a real defect — but a non-destructive diagnostic
proved it does not explain MC20's null result (both orderings ~5 orders of
magnitude below threshold). Not fixed in `scripts/build_mc20_event_gold.py`
this session, because doing so would rebuild MC20 Gold tiles, which this
session's stop conditions treat as protected.

### Phase 2 — CHHAYA input wiring: **PARTIALLY BUILT**
Fixed: `prior_cases_same_corridor` was computed every case and silently
discarded (default 0 regardless of the real SMRITI query result) — now
passed. Wired: `wind_speed_ms`, `area_km2` (both already measured on
`DetectionEvidenceEnvelope`, previously uncollected at the call site),
`elongation` (read from the raw `SlickDetection`, which the envelope doesn't
carry), `phi_available`/`phi_converged` (from the phi_reconstruction stage's
own `convergence_flag`). **Not wired:** `distance_to_shore_km` — the only
adapter (`static_gis.py`) returns a hardcoded `10.0` for every query, and
wiring it would fabricate identical coastal-proximity evidence for every
case. Verified via both demos: Demo B's top hypothesis posterior moved from
0.668 to 0.738 purely from previously-discarded real inputs reaching the
engine.

### Phase 3 — SMRITI hardening: **NOT ATTEMPTED (FUTURE)**
The store/retrieve/corridor-count API already existed and was exercised
(unchanged) via the Phase 2 fix. No new SMRITI capability work this session.

### Phase 4 — Agentic loop observability: **REUSED, not extended**
The fail-closed guard and evidence-delta tracking already existed from the
prior integration session and were exercised, unchanged, by both demo
re-runs. No new loop-level observability work this session — see Phase 7
below for the separate, new case-level observability layer.

### Phase 5 — Authorization / security: **BUILT**
- `apps/api/security.py` (new): `get_principal()` resolves identity from a
  verified JWT (`Authorization: Bearer`) first, falling back to the previous
  unsigned `X-User-Id`/`X-User-Role` headers ONLY when `settings.demo_mode`
  is true. Outside demo mode, unsigned headers are rejected outright — this
  is the concrete change from "interim mechanism, always trusted" to "signed
  path primary, unsigned path opt-in and explicit."
- All 4 previously-unprotected state-changing case endpoints
  (`POST /v1/cases`, `/ingest`, `/reconstruct`, `/attribute`) now require
  `Permission.CREATE_CASE` / `Permission.RUN_CASE_STAGE` (new permission,
  additive to `varuna_infra.rbac`). `missions.py`'s approval endpoint
  migrated onto the same `get_principal()` rather than its own local
  header-only resolver.
- Global `AuthorizationError -> 403` handler added to `apps/api/errors.py` so
  every future route gets this translation for free.
- Fixed a real vulnerability found during Phase 0: `apps/api/routers/cases.py`
  performed `importlib.import_module(f"tests.fixtures.{req.use_fixture}")`
  with `req.use_fixture` taken directly from the request body — production
  code dynamically importing based on unvalidated client input. Replaced with
  an explicit `_FIXTURE_REGISTRY` allowlist.
- 8 new negative-authorization tests (`tests/api/test_cases.py`,
  `tests/unit/test_api_security.py`): unauthenticated 401, wrong-role 403,
  wrong JWT secret 401, expired JWT 401, malformed header 401, demo_mode
  gating both directions. Existing tests were **not weakened** — they were
  updated to authenticate (dependency override for the happy path), which is
  the correct fix for a system that newly requires authentication, not a
  loosened assertion.

### Phase 6 — Canonical workflow enforcement: **VERIFIED + FLAGGED, not migrated**
Confirmed via repo-wide search: `GoldenCaseWorkflow` has zero callers outside
its own module and two test files. `CaseWorkflow` is what every live route
uses. Added a prominent, specific docstring to `case_workflow.py` naming it
non-canonical, naming the exact forcing-realism gap, and naming the migration
path — rather than migrating the API this session, which would mean rewriting
`apps/api/operator_case_view.py` (459 lines, actively owned by another
session's work at time of writing) and risking exactly the "second pipeline"
and "peer collision" failure modes this task explicitly warns against.
**This is the single most consequential open item from this session** — see
the research-questions doc.

### Phase 7 — Observability: **BUILT**
`packages/varuna_infra/observability.py` was, before this session, 13 lines
with zero callers anywhere in the repository — not a hardening target, dead
code. Replaced with: structured JSON logging (`configure_logging`,
`case_logger`), a real thread-safe `MetricsTracker` (was two `pass` stubs),
and `build_case_timeline()`/`summarize_case_state()`, which turn a
`PipelineRun`'s existing `StageResult` objects into an ordered,
human-readable timeline answering "why is this case in this state" — using
only data the pipeline already produced, no new inference. 6 new tests, all
passing. **Not yet wired to an API endpoint** — built and tested, not
exposed; that is Phase 9/10 work.

### Phase 8 — Live data fetch path: **NOT ATTEMPTED (FUTURE)**
ERA5/CMEMS/AIS adapters were verified real (Phase 0). `sentinel1.py` and
`static_gis.py` remain 5-line stubs. No request-planning/retry/cache
orchestration layer was built above the adapters this session.

### Phase 9 — API contract: **PARTIALLY BUILT**
The 4 case-mutation endpoints and the mission-approval endpoint gained
authorization (Phase 5). No new read endpoints were added (evidence ledger,
uncertainty, hypotheses, memory hits, next-action, audit-trail routes named
in the target contract do not exist yet). The observability layer (Phase 7)
is ready to back an audit-trail endpoint but is not yet wired to one.

### Phase 10 — Frontend productization: **NOT ATTEMPTED (FUTURE)**
`apps/web/src/App.tsx` remains 241 lines, single file. None of the six named
operator views exist. This was named in Phase 0 as effectively a from-scratch
build, not an integration, and was not started this session.

### Phase 11 — Two demonstrations: **VERIFIED / RE-RUN**
Both demos already existed from the prior integration session. Both were
re-run this session (not modified) to confirm they still work after this
session's changes, and Demo A's report now reflects the corrected dual-signal
OOD finding. Demo B's CHHAYA posterior shifted from the Phase 2 wiring fix,
confirming the fix actually changes behavior rather than being inert.

### Phase 12 — Evaluation / benchmark: **NOT ATTEMPTED (FUTURE)**
No new benchmark scaffold. The 9 named scenario families and cross-cutting
metrics do not exist as a standing suite.

### Phase 13 — E2E test matrix: **PARTIALLY BUILT**
New tests this session: 8 negative-authorization tests, 6 observability
tests, plus the pre-existing 27 OOD/intelligence tests re-verified against
the new energy-score code path (all pass unchanged). No new coverage for the
negative-test list's other named cases (duplicate case, stale input, live API
timeout, external API failure, memory corruption) this session.

### Phase 14 — UX polish: **NOT ATTEMPTED (FUTURE)**
No frontend exists yet to polish (Phase 10).

### Phase 15 — Scientific language hardening: **VERIFIED**
Spot-checked the language this session's own new code produces
(`ood_energy.py`'s rationale strings, the ADR, this report) against the
named anti-patterns — none found. Did not audit the full pre-existing
codebase's language for compliance; that is a larger sweep not attempted here.

### Phase 16 — Research handoff: **BUILT**
`docs/product/VARUNA_POST_INTEGRATION_RESEARCH_QUESTIONS.md`.

---

## 3. Test state

Baseline at session start: 699 passed / 10 skipped / 4 failed. Of the 4
failures: 1 (`test_netra_training_loop`) is the pre-existing, previously
documented NETRA-owned issue; 3 (`tests/scientific/test_go_nogo_fair_harness.py`)
were newly observed this session, **not caused by anything this session
touched** (confirmed: none of the files that test exercises were modified
here), and are reported rather than investigated or fixed, since they belong
to the fair-harness/scientific track, not this hardening session's scope.

This session added 20 new tests (8 authorization, 6 observability, 6 API
security/JWT — one file, `test_api_security.py`, covers 7 of those), all
passing.

**Regressions found and fixed.** The first full-suite re-run after adding
authorization surfaced 2 genuine regressions this session caused:
`tests/contract/test_operator_case.py` (2 tests) and
`tests/e2e/test_persistent_workflow.py::test_full_workflow_end_to_end` all
called the now-protected case-mutation endpoints with a bare, unauthenticated
`TestClient`. Fixed by adding a scoped `get_principal` dependency override to
each (a fixture with teardown in the e2e file, a helper-with-cleanup in the
contract file — not a module-level override, since `app` is a shared
singleton and an un-torn-down override would leak into other test files in
the same session). **Not fixed by weakening the new authorization
requirement** — these tests were updated to authenticate, which is the
correct fix for a system that newly requires it. Re-run confirmed both files
green; a final full-suite run confirmed no other regressions — see
`reports/product/varuna_product_status.json` for the final count.

---

## 4. Safety verification

- `deleted=0 moved=0 renamed=0 overwritten=0` — every change this session was
  either a new file or an in-place edit to an existing tracked file; nothing
  removed.
- **NETRA checkpoint modified=0** — verified: `git status` on
  `artifacts/checkpoints/` shows no changes; the diagnostic scripts load the
  checkpoint read-only (`torch.load` for inference, never `torch.save`).
- **NETRA Gold modified=0, MC20 Gold modified=0** — verified: `git status` on
  `data/gold/` shows no changes. The channel-binding diagnostic wrote only to
  the session scratchpad, never to `data/gold/events/mc20_v0_1/`.
- **NETRA training files modified=0** — this session never touched
  `packages/varuna_netra/{training,dataset,model}/`, `train_netra.py`, or any
  file in the NETRA-training-owned set named in the session's own
  constraints. (`packages/varuna_netra/model/config.py` shows as modified in
  `git status`, but `git diff` confirms those 3 lines predate this session —
  not touched here.)
- **GPU** — idle throughout (8-9% utilization, ~1.4GB/12GB) at every check
  point; no training process observed at any point this session.
- No secrets or credentials were read, logged, or exposed.

---

## 5. Recommendation for the next session

In priority order, per the dependency graph named in Phase 0:

1. **Resolve or formally accept the `CaseWorkflow`/`GoldenCaseWorkflow` split**
   before building the API contract or frontend on top of either — building
   on the wrong one now is more expensive to unwind later than deciding now.
2. **Wire the fixed channel-binding function into `build_mc20_event_gold.py`**
   and re-freeze MC20 Gold deliberately (not silently) — it's a known-correct
   fix sitting unused next to the code that needs it.
3. Build the request-planning/retry/cache layer above the already-real
   ERA5/CMEMS/AIS adapters (Phase 8) — this and #1 are the two genuine
   prerequisites for a real API contract.
4. Frontend and benchmark are the largest remaining builds and should be
   scoped as their own sessions, not folded into a general hardening pass.
