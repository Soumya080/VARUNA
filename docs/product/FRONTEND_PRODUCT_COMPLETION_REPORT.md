# VARUNA GRID v2 — Frontend Product Completion Report

**Task:** Frontend / Operator Product Integration Track (STEP 5)
**Date:** 2026-09-02

## Final status: **VARUNA_FRONTEND_PRODUCT_READY** (for the P0 scope defined below; see gaps for what is explicitly not)

---

## 1. What existed before this task

- `frontend/VARUNA-frontend_yash`: approved design, 14 pages, wired to real
  backend data for the primary dashboard (`app/page.tsx`) via STEP 4's work
  — `CaseSummary`, `AnalyticalPipeline`, `EvidenceHealth`, `MissionStatus`,
  `RecommendedAction`, and five new intelligence panels (CHHAYA, Uncertainty,
  Decision Trace, SMRITI, PRAMAN).
- `apps/api/routers/replay.py`: `GET /v1/replay/{fixture_name}`, added in
  STEP 4, composing the unified `OperatorCase` via `build_product_case()`.
- Two genuine defects existed, undiscovered until this task's diagnostic:
  the idempotency/intelligence bug and the `.top` type mismatch (§2/§3 of
  the diagnostic report).
- Two buttons ("View Full Intelligence," "Review Evidence") had no
  `onClick` handler at all.

## 2. What was preserved

Zero changes to: theme, color tokens, typography, spacing scale, card
style, navigation structure, page hierarchy, or the component primitive
library (`StatusBadge`, `SectionLabel`, `InfoTip`, `Meter`, `Panel`/`Row`).
Every fix and addition in this task reuses these exactly. `npm run build`
confirms all 14 routes still prerender unchanged in count and shape.

## 3. What was changed, and why each change was necessary

| Change | File(s) | Why (use-case justification, per this task's §2 rule) |
|---|---|---|
| `run_replay_case(..., force=True)` | `apps/api/routers/replay.py` | Without it, intelligence silently disappeared after the first request of a server's lifetime — a real, high-impact functional regression, not a cosmetic issue |
| Regression test rewrite | `tests/api/test_replay_endpoint.py` | The old test asserted an invariant (`artifact_ids` equality) that is no longer true and was never the actual guarantee that mattered; rewritten to assert the guarantee that does matter (scientific content stability) |
| Removed `top` from `SourceHypothesisEnvelopeValue` | `lib/operator-case-types.ts` | The field never exists in real API responses; leaving it typed as required would eventually cause a real runtime `undefined` bug for any future code that trusted the type |
| Wired `onClick` on "View Full Intelligence" | `case-intelligence.tsx` | Phase 5's explicit rule: no visible primary action may silently do nothing. Scrolls to real, already-present content — not a new page, not a redesign |
| Wired `onClick` on "Review Evidence" | `mission-status.tsx` | Same rule, same fix pattern |
| Added `id`/`scroll-mt-14` to the `Panel` primitives | `case-intelligence.tsx`, `intelligence-panels.tsx` | Minimal structural change (an `id` attribute and one utility class) needed to make the two fixes above actually work; does not alter any visual appearance |

No layout was rearranged, no card was resized, no navigation model changed.
Every change above is the smallest structural addition that makes an
already-existing, already-designed piece of content reachable or correct.

## 4. APIs integrated

`GET /v1/replay/{fixture_name}` (fixed this task), `GET /v1/replay/fixtures`
— both via `lib/api.ts`, the single centralized typed client (unchanged
architecture from STEP 4: base URL, error normalization into `ApiError`,
one `getJson<T>()` helper every function reuses).

## 5. Interactions fixed

See `docs/product/FRONTEND_RUNTIME_DIAGNOSTIC.md` §4 for the full inventory.
Two silently-broken buttons fixed; one intentionally-disabled button
reconfirmed correct; all other interactive elements verified already
correct.

## 6. Case workflow

`CASE-VALID` → `GoldenCaseWorkflow.run_replay_case(force=True)` →
`build_product_case()` → `OperatorCase` (now reliably including
`.intelligence`) → `OperatorCaseProvider` (React context, one fetch) →
every wired component. Verified end-to-end via live HTTP after every code
change in this session, not assumed from the previous task's verification.

## 7. Intelligence surfaces

CHHAYA, Uncertainty, Decision Trace, SMRITI, and PRAMAN panels (built in
STEP 4) now render REAL data on **every** page load, not just the first —
this is the direct, verified consequence of the idempotency fix. Confirmed
by 3 consecutive live requests all showing `intelligence.status: "produced"`.

## 8. Alerts

Unchanged from STEP 4: `OperatorCase.alerts` is available from the API but
not rendered anywhere in the wired UI. This remains an explicit, named gap
(§14), consistent with this task's P0/P1/P2 priority ordering, which does
not name alerts as P0.

## 9. Mission

Real mission id/state/asset/approval fields render (STEP 4). Authorization
button remains honestly disabled (verified still correct this session) —
per §8's explicit instruction, the frontend does not fake authorization.

## 10. Provenance

`PramanPanel` (STEP 4) shows real artifact IDs, model versions, and the
evidence lineage list. `manifest_artifact_id` correctly shows the honest
"not yet registered" state (unchanged gap from STEP 2/3, backend-side, out
of this task's scope per §16's endpoint-addition criteria).

## 11. Map

Unchanged. `CASE-VALID`'s AIS section is genuinely `NOT_YET_PRODUCED` (zero
tracks) — the existing mock vessel-track visualization was deliberately
left as-is rather than wired to an empty real result that would be visually
indistinguishable from "broken," per this task's own §12 instruction
("if AIS is unavailable, show Unavailable rather than inventing geometry" —
the map does not currently render an explicit unavailable state either,
which is named as a gap, not silently accepted as fine).

## 12. REAL/REPLAY/SIMULATED handling

Unchanged from STEP 4, reconfirmed working this session:
`EngineModeBadge`/`EvidenceModeBadge` remain two distinct components with
non-overlapping tone tables, verified by 6 passing Vitest tests including
two specifically checking `ENGINE_MODE_TONE.replay !== ENGINE_MODE_TONE.real`
and the equivalent for `EVIDENCE_MODE_TONE`.

## 13. Loading/error states

Unchanged from STEP 4 (`OperatorCaseBoundary`), reconfirmed still correct.

## 14. Browser verification

**Distinguished explicitly, per this task's §18/§22 instruction:**

- **Build verification:** `npx tsc --noEmit` (0 errors), `npm run build`
  (0 errors, 14/14 routes prerendered) — both re-run after every fix in
  this session.
- **HTTP verification:** live `curl` round-trips against the running
  backend before and after each fix, confirming the exact JSON shape
  returned matches what the frontend types expect, and confirming the
  idempotency bug's presence and then its absence.
- **Browser/manual verification:** **not performed** — no browser
  automation tool exists in this environment. The dev server's own request
  log was inspected instead (`GET /`, `/cases`, `/detection`, `/intelligence`,
  `/evidence-chain`, `/missions`, `/alerts` all `200`, multiple successful
  hot-reload compiles after each edit, zero errors logged). This is real
  evidence of a working server, but it is **not** the same as a human
  confirming the CHHAYA panel visually renders correctly, that the scroll
  behavior feels right, or that no CSS regression is visible. Both dev
  servers are left running (backend `127.0.0.1:8000`, frontend
  `localhost:3000`) specifically so a human can do this final check.

## 15. Tests

- Backend: `tests/api/test_replay_endpoint.py` — 7 tests (was 6; the
  idempotency-artifact test was replaced by two more precise tests). All
  passing.
- Frontend: `lib/__tests__/operator-case-integration.test.ts` — 6 tests,
  unchanged from STEP 4, all still passing.
- Full backend regression: **757 passed, 10 skipped, 1 pre-existing
  failure** (`test_netra_training_loop`, unrelated). Baseline before this
  task was 756/10/1 (STEP 4's final count) — +1 net (one test replaced by
  two, one of the two also closing the artifact-ID assumption gap). Zero
  regressions.

## 16. Remaining gaps (explicit, not hidden)

1. **`apps/web/` remains functionally inert** — no case-creation UI, so its
   case list is always empty against the in-memory backend. Named in the
   diagnostic report; not fixed, since `frontend/VARUNA-frontend_yash` is
   the actual product surface this and the prior task built on.
2. **13 of 14 pages remain on mock data** (unchanged from STEP 4) — P1/P2
   per this task's own priority ordering, not attempted.
3. **Alerts are not rendered anywhere** in the wired UI, despite being
   available from the API.
4. **Map/AIS visualization** does not render an explicit "Unavailable"
   state when AIS is empty — it silently continues showing mock vessel
   tracks. This is a real, named gap against this task's own §12
   instruction, not previously called out this precisely.
5. **No human browser walkthrough performed** — see §14.
6. **The exact user-reported 404 was not independently reproduced** through
   any currently-wired frontend control — see the diagnostic report §1 for
   the full reasoning and the most likely (but not certain) explanation.

## 17. Regression

**757 passed, 10 skipped, 1 pre-existing unrelated failure. Zero
regressions.**
