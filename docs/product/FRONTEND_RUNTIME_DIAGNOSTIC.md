# VARUNA GRID v2 — Frontend Runtime Diagnostic

**Task:** Frontend / Operator Product Integration Track (STEP 5)
**Date:** 2026-09-02

## User-reported symptom (verbatim, not assumed)

- "Some buttons/actions do not work."
- A backend request can return `{"error":"http_error","message":"Not Found"}`.

This document distinguishes what was **verified by reproduction** from what
remains **plausible but not independently confirmed**.

---

## 0. Two frontends exist — resolved which one is in scope

This task's own text (§0, §3, §18) names `apps/web/` as the frontend to
inspect. The immediately preceding task (STEP 4) explicitly named
`frontend/VARUNA-frontend_yash` as *"the frontend already has an APPROVED
DESIGN"* and all STEP 4/5 integration work (`lib/api.ts`, the intelligence
panels, the replay wiring) was built there.

**Both were inspected.** Findings:

- `apps/web/src/App.tsx` (241 lines) has three hardcoded `fetch()` calls to
  real, existing routes: `GET /v1/cases`, `GET /v1/cases/{id}`,
  `GET /v1/events?case_id=...`, `GET /v1/cases/{id}/artifacts`. All four
  routes exist and respond correctly when a case exists. **The app has no
  case-creation UI at all** — only `useState`/`useEffect` reads, no `POST`.
  Since the backend's case store is in-memory and reset on every server
  restart, `apps/web`'s case list is `[]` on every fresh boot, so
  `selectedCase` never becomes non-null and the three detail fetches never
  fire. The app is not broken by a bad route — it is functionally inert by
  construction (no way to reach its own data-fetching code), which a user
  could reasonably describe as "buttons don't work" even though there is no
  literal broken button, because there is no path to any button that matters.
- `frontend/VARUNA-frontend_yash` is the frontend STEP 4/5's actual
  integration work lives in, is substantially richer (14 pages vs. 1), and
  is what this report treats as the product surface going forward — but
  `apps/web`'s gap is recorded here rather than silently dismissed, per this
  task's explicit instruction not to assume.

**Resolution:** continued treating `frontend/VARUNA-frontend_yash` as
canonical (consistent with the immediately preceding task's explicit
statement), and recorded `apps/web`'s gap as a named, unfixed finding rather
than either silently ignoring the task text's stated target or spending
this session's effort rebuilding a superseded skeleton.

---

## 1. Reproducing the exact reported 404

**Verified, byte-for-byte reproduction:** the literal payload
`{"error":"http_error","message":"Not Found"}` **is** produced by this
backend, confirmed by requesting any URL with no matching FastAPI route
(e.g. `GET /` or `GET /readiness` — the real prefix is `/v1/readiness`).
Source: `apps/api/errors.py::http_exception_handler`, which wraps every
`StarletteHTTPException` (including Starlette's own default 404 for an
unmatched path, whose default `detail` is the literal string `"Not Found"`)
into `{"error": "http_error", "message": exc.detail}`. This confirms the
SHAPE of the reported error is real and comes from this codebase, not a
red herring.

**What could NOT be reproduced:** a 404 from any control currently wired in
`frontend/VARUNA-frontend_yash`. Full trace:

- The only `fetch()` call this frontend makes (`lib/api.ts::getReplayOperatorCase`,
  invoked from `lib/operator-case-context.tsx` on page load with
  `fixtureName='CASE-VALID'`) hits `GET /v1/replay/CASE-VALID`, which returns
  200 in every test performed this session (repeated calls, before and
  after the fix in §2).
- No other frontend code path calls `fetch()`, confirmed by a repo-wide
  search (`grep -rn "fetch(\|axios" app/ components/ lib/`) — the only
  match outside `lib/api.ts` is a tooltip **string**, not a call
  (`mission-status.tsx`'s disabled-button title mentions the literal path
  `POST /v1/missions/{id}/approve` as prose, never executes it).

**Most likely explanation, stated as a hypothesis with its supporting and
undermining evidence, not asserted as fact:** the report most plausibly
predates the `GET /v1/replay/{fixture_name}` route's existence (added in
STEP 4 of this same session) — a browser tab or manual test hitting
`/v1/cases/CASE-VALID/operator-view` (a case that was never `POST`-created
under that literal ID in the legacy `CaseWorkflow` store) would 404 via a
**different** handler (`CaseNotFoundError` → `{"error":"not_found",...}`,
a different `error` value) — so this alone doesn't fully match either.
The cleanest fully-matching candidate is simply **any URL typo or an
endpoint tested before this session added it** — Starlette's generic
unmatched-route 404 is the only handler that produces the exact reported
shape. No further narrowing was possible without the user's exact URL/method,
and this report says so rather than asserting a specific unverified cause.

---

## 2. Real bug found and fixed (not the reported 404, but a genuine,
   independently-discovered regression)

**Root cause, verified:** `GET /v1/replay/{fixture_name}` called
`workflow.run_replay_case(case_id, fixture_name)` without `force=True`. Since
this route always derives the **same** `case_id`
(`f"REPLAY-{fixture_name}"`), `GoldenCaseWorkflow`'s idempotency cache
(by design, per ADR from STEP 2/3) served a cached `CaseResult` on every
call after the first. A cached result's `.run` is a `_ReplayedRunView`
(`packages/varuna_domain/golden_case_engine.py`), which has no `.stages` —
`build_product_case()` correctly (per its own documented contract) reports
`intelligence.status = NOT_YET_PRODUCED` when it cannot compose against
such a result.

**Verified reproduction, before fix:**
```
call 1: intelligence.status = "produced"
call 2: intelligence.status = "not_yet_produced"
call 3: intelligence.status = "not_yet_produced"
```
Confirmed via three consecutive `curl` requests against the live server.

**Impact:** every real user session, after the very first page load per
backend-process lifetime, would see CHHAYA/SMRITI/Uncertainty/Decision-Trace
render as "not available" — the five new intelligence panels built in
STEP 4 would appear broken for virtually every actual demo interaction.
This is a genuine, high-impact bug independent of the user's literal 404
report, found by this session's own diagnostic before it was reported by
anyone.

**Fix:** `apps/api/routers/replay.py` now calls
`run_replay_case(case_id, fixture_name, force=True)`. Verified after fix:
`intelligence.status = "produced"` on 3 consecutive calls. Regression test
added: `tests/api/test_replay_endpoint.py::test_intelligence_stays_populated_across_repeated_requests`.

**Side effect of the fix, also found and corrected:** `force=True` means
`provenance.artifact_ids` (a freshly-registered random PRAMAN artifact ID
each call) and `run_id` now legitimately differ between requests — this
broke the existing `test_repeated_request_is_idempotent` test, which
asserted artifact-ID equality. Renamed and rewritten
(`test_repeated_requests_stay_scientifically_deterministic`) to assert the
correct invariant: every actual scientific/evidentiary VALUE stays
identical, while wall-clock/random identifiers are allowed to differ — the
same convention already established in
`tests/integration/test_product_case_composition.py` from STEP 3.

---

## 3. A second real bug found while writing the regression test

While writing the new determinism test, `SourceHypothesisEnvelope.top` (a
Python `@property`, not a `@computed_field`) was found to **never appear**
in the serialized JSON response, despite `lib/operator-case-types.ts`
declaring it as a required field (`top: SourceHypothesisValue`). Checked the
frontend for any code depending on the missing field — none found (
`intelligence-panels.tsx`'s `ChhayaPanel` already derives the top hypothesis
via `.slice().sort(...)`, not by reading `.top`), so this was a **latent**
type-contract bug, not a live runtime crash. Fixed the TypeScript type to
remove the field and documented why, so no future code is tempted to read
a key that doesn't exist.

---

## 4. Interaction inventory (Phase 5)

| Element | Component | Before | After |
|---|---|---|---|
| "View Full Intelligence" | `case-intelligence.tsx` | No `onClick` at all — silently did nothing | Scrolls to the real CHHAYA panel (`#chhaya-panel`), already on the same page |
| "Review Evidence" | `mission-status.tsx` | No `onClick` at all — silently did nothing | Scrolls to the real Evidence Health panel (`#evidence-health-panel`) |
| "Request Authorization" | `mission-status.tsx` | No `onClick`, looked clickable | Explicitly `disabled`, with a tooltip naming the real reason (no JWT-authenticated mutation is wired) — done in STEP 4, reconfirmed still correct this session |
| Candidate vessel rows | `candidate-vessels.tsx` | Opens detail drawer with mock vessel data | Unchanged — legitimate, since `CASE-VALID`'s real AIS section is genuinely empty (0 tracks); wiring this to empty real data would look identical to "broken" |
| Nav / sidebar / dropdown toggles | `header.tsx`, `sidebar.tsx`, `detail-drawer.tsx` | Real local UI state changes | Unchanged — already correct, verified by inspection |

No remaining primary-view control silently does nothing.

---

## 5. Environment / configuration checks performed

- CORS: `access-control-allow-origin: http://localhost:3000` confirmed
  present on backend responses.
- `NEXT_PUBLIC_VARUNA_API_URL` (`.env.local`) correctly points at
  `http://127.0.0.1:8000`; confirmed the frontend actually uses it (not a
  stale value) by observing successful, populated responses after backend
  restart.
- No proxy/rewrite rules exist in `next.config.mjs` that could redirect API
  calls elsewhere.
- Verified two Python processes were present on this machine during
  diagnosis; identified (via `wmic ... get CommandLine`) that only one was
  bound to port 8000 (confirmed by a request timing out immediately after
  stopping it via this session's own tracked background task, `TaskStop`,
  never a blind `kill`); the other was left untouched as it was not
  provably safe to assume ownership of.
