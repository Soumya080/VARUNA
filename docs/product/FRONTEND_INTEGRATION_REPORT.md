# VARUNA GRID v2 — Frontend Integration Report

**Task:** STEP 4, Frontend Track — Unified Operator Case → Frontend Integration
**Date:** 2026-09-02
**Frontend:** `frontend/VARUNA-frontend_yash` (Next.js 16 / React 19 / Tailwind 4)
**Backend addition:** `GET /v1/replay/{fixture_name}` (ADR-0014)

## Final status: **VARUNA_FRONTEND_INTEGRATED**

---

## 0. Housekeeping before this task began

`frontend/` contained two copies: `VARUNA-frontend_yash` (the real, approved
design — 14 pages, ~4,800 lines) and `__MACOSX` (35 MB of macOS
zip-extraction metadata junk, confirmed via `file` as "AppleDouble encoded
Macintosh file," zero real content). `frontend/` was entirely untracked, so
removing `__MACOSX` was safe and lossless. `VARUNA-frontend_yash` is the one
frontend this task builds on.

## 1. Existing design preserved

No theme, palette, typography, spacing, card style, or navigation change.
Every new visual element (`EngineModeBadge`, `EvidenceModeBadge`, the five
new intelligence panels, the loading/error boundary) reuses the SAME
primitives the existing design already had: `StatusBadge`, `SectionLabel`,
`InfoTip`, `Meter`, the `Panel`/`Row` layout pattern from `case-intelligence.tsx`.
No new component library, no new font, no new color token was introduced.
`npm run build` confirms all 14 existing routes still prerender unchanged.

## 2. Phase 1 — API composition verification (the required check before any UI work)

Confirmed by direct inspection: `GET /v1/cases/{case_id}/operator-view` does
**not** return the unified representation — it is still backed by the legacy
`CaseWorkflow` (STEP 1, unchanged), which produces no `PipelineRun` for
`CaseIntelligenceService` to compose against. No existing route of any kind
ran a case through `GoldenCaseWorkflow`.

**Smallest safe addition** (not a backend redesign, not a competing schema):
`apps/api/routers/replay.py`, `GET /v1/replay/{fixture_name}`, returning the
SAME `OperatorCase` model every other route returns, composed via
`build_product_case()` (ADR-0013). Full reasoning in
`docs/architecture/ADR-0014-frontend-replay-endpoint.md`. Verified: 6 new
backend tests pass; the existing `/operator-view` route and its tests are
untouched.

## 3. Pages/components enhanced

**Enhanced with real data** (the Overview/Dashboard page, `app/page.tsx`,
per Phase 2's explicit "make ONE populated replay case render correctly"
instruction — not every page):

| Component | What changed |
|---|---|
| `app/page.tsx` | Wrapped in `OperatorCaseProvider` (fetches `CASE-VALID`); added `EngineModeBadge` to the heading |
| `case-summary.tsx` | Observation, origin, attribution, validity now read from the real `OperatorCase`; drift-window kept as the existing placeholder (no backend field exists for it) |
| `analytical-pipeline.tsx` | The 6-stage timeline now derives from real `OperatorCase` sections (detection/origin/attribution/validity/forecast/mission), each showing real status + evidence_mode |
| `evidence-health.tsx` | Gauge and breakdown now read `OperatorCase.evidence.components`; a `null` score renders "—" and a muted bar, never a fabricated 0% or 100% |
| `mission-status.tsx` | Real mission id/state/asset/approval status shown in a new summary row; "Request Authorization" button disabled with an honest tooltip (see §7) |
| `case-intelligence.tsx` | "Recommended Action" now reflects the real `recommendation` + validity reason; 5 new panels added (below) |
| `intelligence-panels.tsx` (new file) | CHHAYA, Uncertainty, Decision Trace, SMRITI, PRAMAN panels — all new, all real data |

**Not enhanced this task** (remain on mock data, explicitly not expanded
into per Phase 2's "do not attempt every page first"): `cases`, `detection`,
`evidence-chain`, `intelligence`, `missions`, `alerts`, `assets`, `reports`,
`vessel-attribution`, `source-reconstruction`, `assignment-mission` pages,
and the map/vessel-track visualization components. See §12 for the full
classification.

## 4. Unified API contract used

`GET /v1/replay/CASE-VALID` → `varuna_contracts.operator_case.OperatorCase`
(schema `v1`, including the STEP-3 `.intelligence` field). TypeScript mirror:
`lib/operator-case-types.ts`. Client: `lib/api.ts`. Data flow:
`OperatorCaseProvider` (context, one fetch per page) → `useOperatorCaseData()`
(consumed by every wired component) → `OperatorCaseBoundary` (loading/error
states).

## 5. Backend composition used

`build_product_case(result, workflow, smriti=...)` — the STEP-3 composition
function, unmodified. The new endpoint's ONLY job is to call
`GoldenCaseWorkflow.run_replay_case()` then this function; no new scientific
or reasoning logic anywhere in the request path.

## 6. Data states

`ProducerStatus` (`produced`/`not_yet_produced`/`blocked`) rendered
honestly throughout: `AnalyticalPipeline` shows each stage's real status;
`EvidenceHealth` shows `null` (unmeasured) distinctly from `0` (measured
and low); `CaseSummary`'s fields show `—` with the real backend `reason`
string, never a fabricated value. `OperatorCaseBoundary` handles
loading/error at the page level; component-level `not_yet_produced` states
are handled per-section, matching the backend's own three-state model
(never collapsed to a boolean "ok/not ok").

## 7. Alert integration

Not built this task — the Overview/Dashboard page has no alert panel in the
existing design (alerts live on the dedicated `/alerts` page, which remains
on mock data). `OperatorCase.alerts` IS available in the fetched data
(confirmed via the live endpoint) but is not yet rendered anywhere. Named
as a gap, not silently skipped — see §12.

## 8. Mission integration

`MissionStatus` now shows the real mission's `mission_id`, `state`,
`asset_id`, and `approved_by`. The "Request Authorization" button is
**disabled** rather than wired to a fake success: real authorization
requires an authenticated `POST /v1/missions/{id}/approve` call (JWT), which
this milestone does not implement (would require a login flow — explicitly
larger than "the minimum necessary backend fix" this task's scope allows).
Per Phase 10's explicit instruction ("do not simulate successful
authorization"), disabling the button with a clear reason is the correct
choice over a button that lies.

## 9. Evidence visualization

`EvidenceHealth` (existing gauge component, now real data) +
`PramanPanel`'s "Evidence lineage" list (new — `EvidenceModeBadge` per item,
`OperatorCase.intelligence.evidence_lineage`, from `EvidenceLedger.audit_trail()`).
Full ledger contradiction/support graph is not visualized (only the flat
audit trail) — named as a gap.

## 10. Uncertainty visualization

`UncertaintyPanel` (new): each of the six `UncertaintyAssessment` components
(model confidence, data quality, evidence agreement, attribution
uncertainty, forecast uncertainty, decision confidence) rendered as its own
row, plus OOD risk as a distinct colored badge and a conflict-count badge
when non-zero. Never collapsed into one score, per Phase 13's explicit
requirement — verified by the panel's own structure (six independent rows,
no aggregate computed).

## 11. Real / Replay / Simulated handling

`EngineModeBadge` (page heading) and `EvidenceModeBadge` (per-section,
compact form used throughout the intelligence panels and evidence lineage
list) are two DISTINCT components with two distinct tone tables — verified
never to collide by a dedicated test
(`ENGINE_MODE_TONE.replay !== ENGINE_MODE_TONE.real`,
`EVIDENCE_MODE_TONE.simulated/unavailable !== EVIDENCE_MODE_TONE.real`).
`CASE-VALID` renders `engine_mode = REPLAY` (warn/amber tone) alongside
section `evidence_mode = REAL` (ok/green tone) simultaneously and legibly —
this is the concrete proof of Phase 5's requirement, not an assertion about it.

## 11a. Backend regression

Full suite (`pytest tests/ -q --ignore=tests/scientific`): **756 passed, 10
skipped, 1 pre-existing failure** (`test_netra_training_loop`, unrelated).
Confirmed against the 750/10/1 baseline inherited from STEP 3: +6 from the
new `tests/api/test_replay_endpoint.py`. Zero regressions.

## 12. Tests

- **Backend:** `tests/api/test_replay_endpoint.py` — 6 tests, all passing.
- **Frontend:** `lib/__tests__/operator-case-integration.test.ts` (Vitest,
  newly added — no test framework existed before) — 6 tests: EvidenceMode/
  engine_mode label and tone-collision checks, API client error handling
  (unreachable backend, 404 detail passthrough, malformed error body). Run
  via `npm run test`.
- **Static verification:** `npx tsc --noEmit` — zero errors. `npm run
  build` — zero errors, all 14 routes prerender successfully.

## 13. Local preview verification

- Node.js was not installed on this machine; installed Node LTS (v24.19.0)
  via `winget` with explicit user confirmation before proceeding (a
  system-level change, flagged and approved rather than assumed).
- `npm install` — 362 packages, 0 vulnerabilities.
- Backend: `uvicorn apps.api.main:app` on `127.0.0.1:8000` — confirmed live,
  confirmed `GET /v1/replay/CASE-VALID` returns real, populated data.
- Frontend: `npm run dev` (Turbopack) on `localhost:3000` — confirmed
  `✓ Ready`, zero compile errors in the dev server log.
- CORS confirmed correct (`access-control-allow-origin: http://localhost:3000`
  present on the backend's response).
- All 14 routes (`/`, `/cases`, `/detection`, `/intelligence`,
  `/evidence-chain`, `/missions`, `/alerts`, etc.) return HTTP 200 with no
  server-side errors logged.
- SSR output for `/` confirmed to contain the correct loading-boundary text
  (`"Loading case from VARUNA backend"`), proving the fetch/boundary wiring
  activates before client hydration.

**Limitation, stated plainly:** this environment has no browser automation
tool (no Playwright/Puppeteer/Selenium installed, and none was added, per
"do not create a large testing framework unnecessarily"). Verification was
therefore: (a) static type-checking, (b) production build success, (c) live
HTTP round-trips against both servers confirming the real data contract
matches the TypeScript types, (d) SSR output inspection, (e) dev-server log
inspection for runtime errors during route generation. A human visually
opening `http://localhost:3000` in an actual browser has **not** been done
by this agent and should be the final confirming step before considering
this fully closed — the dev server is left running for exactly that purpose
(see §"Servers left running" below).

## 14. Remaining gaps

Honest, itemized, not silently expanded or silently skipped:

1. **13 of 14 pages remain on mock data** (`cases`, `detection`,
   `evidence-chain`, `intelligence`, `missions`, `alerts`, `assets`,
   `reports`, `vessel-attribution`, `source-reconstruction`,
   `assignment-mission`, and the map/vessel visualization components). This
   was Phase 2's explicit instruction ("do NOT attempt to build every page
   first"), not an oversight.
2. **Alerts are not rendered anywhere** despite `OperatorCase.alerts` being
   available from the live endpoint.
3. **Mission authorization is display-only** — the button is honestly
   disabled, not wired to a real mutation (would need a login/JWT flow).
4. **Map/AIS visualization untouched** — `CASE-VALID`'s AIS section is
   legitimately `NOT_YET_PRODUCED` (zero tracks), so the map's vessel-track
   mock data was left alone rather than wired to an empty real result that
   would look identical to "not implemented."
5. **No human browser walkthrough performed** — see §13's limitation note.
6. **Evidence Ledger contradiction/support graph** is not visualized, only
   the flat audit-trail list.

## Servers left running for preview

- Backend: `http://127.0.0.1:8000` (uvicorn, background task)
- Frontend: `http://localhost:3000` (Next.js dev server, background task)

Both were left running per Phase 14's "keep the local server running for
preview when possible" instruction.
