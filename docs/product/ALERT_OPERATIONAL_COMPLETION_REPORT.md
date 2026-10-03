# VARUNA GRID v2 — Alert Orchestrator + Operational Response Loop

**Task:** Integration Track STEP 6
**Date:** 2026-09-02

## Final status: **ALERT_OPERATIONAL_VERIFIED** (with documented remaining gaps — see §12)

---

## 1. Diagnosis (Phase 0)

Full trace in `docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md`. Headline findings:

- Mission **authorization enforcement** (`MissionService.approve_and_assign`) was
  already backend-authoritative, JWT-based, and correct — built in an earlier
  session. Nothing needed rebuilding there.
- Mission **authorization audit** was silently discarded on every request:
  `get_mission_service()` constructed a fresh `MissionService` (and therefore a
  fresh, empty `AuditLog`) per call. This task fixes it (§4).
- Materiality/severity/dedupe/role-routing existed and were correct, but only
  one event type (`validity.evaluated`) was ever actually wired into the
  pipeline, and there was no alert **entity** at all — `DeliveryResult` is a
  delivery receipt, not something an operator can acknowledge.
- `OperatorCase.alerts` (the read contract) was already fully honest and
  correct; it simply had no lifecycle to reflect.
- Both frontend nav pages (`/alerts`, `/missions`) were 100% hardcoded mock
  arrays, fully disconnected from the backend.

## 2. What was built (the smallest legitimate set)

| Component | File |
|---|---|
| `AlertRecord` + `AlertLifecycleStatus` (CREATED→ACKNOWLEDGED→ESCALATED→RESOLVED) | `packages/varuna_alerts/lifecycle.py` |
| Per-case alert store | `packages/varuna_alerts/lifecycle_store.py` |
| `AlertLifecycleService` — correlates `DeliveryResult`s into one `AlertRecord` per case+event (Phase 4 dedup/correlation), enforces RBAC via the existing `authorize()` (Phase 8's pattern reused, not reinvented) | `packages/varuna_alerts/lifecycle_service.py` |
| 3 new RBAC permissions (`ACKNOWLEDGE_ALERT`, `ESCALATE_ALERT`, `RESOLVE_ALERT`); DUTY_OFFICER/ADMIN get all three, ANALYST gets acknowledge only | `packages/varuna_infra/rbac.py` |
| `GoldenCaseWorkflow._sync_alerts_to_lifecycle()` — correlates the `alerts` stage's output into the lifecycle store and registers a PRAMAN artifact, on every fresh run (both REAL and REPLAY, since both pass through `_finalize`) | `packages/varuna_domain/golden_case_engine.py` |
| Fixed mission audit-discard bug: `get_mission_service()` is now a singleton with a persistent `AuditLog` | `apps/api/dependencies.py` |
| New API: `GET /v1/cases/{case_id}/alerts`, `GET /v1/alerts/{alert_id}`, `POST /v1/alerts/{alert_id}/{acknowledge,escalate,resolve}`, `GET /v1/missions/{id}/audit` | `apps/api/routers/alerts.py`, `apps/api/routers/missions.py` |
| Real Alert Center (`/alerts`) and Mission Control (`/missions`) pages, replacing hardcoded mock arrays; `mission-status.tsx`'s "Request Authorization" button now genuinely calls the backend instead of being permanently disabled | `frontend/VARUNA-frontend_yash/app/alerts/page.tsx`, `app/missions/page.tsx`, `components/mission-status.tsx`, `lib/api.ts` |

No file in `varuna_nyaya`, `varuna_prativartan`, `varuna_pravaah`, or NETRA was
touched. No second alert store, mission store, or pipeline was created —
`AlertLifecycleService` reads the same `DeliveryResult`s the existing
`AlertService`/pipeline already produce; `MissionService`/`MissionRecord` are
completely unchanged except for the audit-singleton fix.

## 3. Material-change engine (Phase 1)

Unchanged from diagnosis: the pipeline still only wires `validity.evaluated`
into `route_and_send()`. Expanding to the other three recognized event types
(`attribution.generated`, `mission.assigned`, `landfall.predicted`) would
require instrumenting three more pipeline stages to call `route_and_send()` —
a real, separable follow-on, not attempted here to keep this task's surface
area to what could be fully verified. `check_materiality()` already blocks
non-material events and RESTRICTED/INCONCLUSIVE gate states, so no new alerts
were added for the sake of adding them.

## 4. Alert contract (Phase 2)

`AlertRecord`: `alert_id`, `case_id`, `event_type`, `severity`, `reason`,
`is_simulated`, `evidence_mode`, `deliveries` (the underlying evidence),
`correlation_key`, `status`, and per-transition actor/timestamp fields. No
field is invented beyond what `DeliveryResult`/the alerts stage already
report — `event_type` is honestly `"unknown"` for the replay fixture, whose
own `StageResult.detail` does not carry it (deliberately not parsed out of
`idempotency_key`, matching `AlertView.category`'s own established caution
against relying on a channel-specific key format).

## 5. Severity (Phase 3)

Unchanged, reused verbatim (`varuna_alerts.severity.infer_severity`) —
already correctly separates severity from confidence and already documents
why CRITICAL is unreachable (no urgency-scoring policy exists in this
repository; inventing one was explicitly out of scope).

## 6. Deduplication / correlation (Phase 4)

`AlertLifecycleService.sync_from_deliveries()` is keyed by `case_id:event_type`
and updates the existing `AlertRecord`'s deliveries in place on a repeated
sync rather than creating a duplicate — verified by
`test_repeated_sync_correlates_instead_of_duplicating`.

## 7. Role routing (Phase 5)

Unchanged (`varuna_alerts.role_router.ROLE_ROUTING`). New: RBAC now gates the
*lifecycle actions* (who may acknowledge/escalate/resolve), reusing
`varuna_infra.rbac`/`authorize()` exactly as `MissionService` already does —
no second authorization mechanism.

## 8. Alert lifecycle (Phase 6)

`CREATED → ACKNOWLEDGED → ESCALATED → RESOLVED`, with `ACKNOWLEDGED → RESOLVED`
also legal (an operator may resolve directly after acknowledging, without
escalating). Every transition is authorized before mutation and is illegal
once past `RESOLVED` — verified by `test_illegal_transition_is_rejected`.

## 9. API (Phase 7)

All five new routes use `apps.api.security.get_principal` (the real JWT/demo
header resolver already used by `/v1/missions/{id}/approve`) — no new
authentication mechanism. Denials return 403 (not 404), matching the
existing mission-approval convention so a denial is never masked as
"resource doesn't exist."

## 10. Mission authorization (Phase 8)

Already verified correct in diagnosis; this task adds:
- **The audit-discard fix** (§2) — the single blocking gap.
- `GET /v1/missions/{id}/audit`, so "who was denied / who approved" is now
  answerable, live-verified via `curl`: an unauthenticated approval attempt
  against a real mission returns 401 with a persistent audit record still
  showing DENIED on a subsequent audit read.
- New regression test `test_mission_audit_persists_across_requests`.

## 11. Frontend (Phase 9)

- `/alerts`: fetches `GET /v1/cases/{case_id}/alerts` for the CASE-VALID
  replay case; shows severity, event type, reason, case, created timestamp,
  evidence mode, and lifecycle status; Acknowledge/Escalate/Resolve buttons
  call the real endpoints and render **"NOT AUTHORIZED"** inline on a 401/403
  rather than silently failing or pretending to succeed.
- `/missions`: shows the real `OperatorCase.mission` for CASE-VALID
  alongside the real, separately-sourced `GET /v1/missions` list from
  `MissionService` — documented as two distinct data sources rather than
  merged into one fabricated list (§12). "Approve"/"View Audit" buttons call
  the real API.
- `components/mission-status.tsx`'s sidebar "Request Authorization" button
  now genuinely attempts the backend call (previously permanently disabled)
  and reports the real outcome.
- Existing visual design/layout/nav preserved; only the data source and
  action wiring changed.

## 12. Known, documented remaining gaps

1. **No login/token-issuing endpoint exists in this deployment**
   (`apps/api/security.py`'s own long-standing docstring), and `demo_mode`
   is `false` in `.env`. Every lifecycle/mission action from the frontend
   therefore genuinely returns 401 today — verified live via `curl`. This is
   the correct, honest state per this task's own Phase 9 instruction ("must
   NOT imply recommendation = authorization... must not fake mutation"), not
   a bug this task introduces or is scoped to fix (building a real login
   system was not requested and is out of scope).
2. The replay fixture's `MissionRecord` (surfaced via `OperatorCase.mission`)
   and `MissionService`'s live store are two separate records for the same
   conceptual mission — the replay pipeline builds its `MissionRecord`
   directly rather than through `MissionService.create_mission()`. Approving
   a mission via `/missions` therefore does not change what
   `OperatorCase.mission` shows for the replay case. Documented on the
   frontend page rather than silently merged.
3. Only `validity.evaluated` triggers a real alert in the pipeline today
   (§3) — the other three recognized material event types are dead code
   paths pending future stage instrumentation.
4. PRAMAN records alert correlation and delivery data (via
   `_sync_alerts_to_lifecycle`), but mission approval/denial audit lives
   only in `MissionService.audit_log` (in-memory, process-lifetime), not yet
   registered as a PRAMAN artifact — `GET /v1/missions/{id}/audit` answers
   the auditability requirement without that additional wiring; folding it
   into PRAMAN is a natural next step, not attempted here to avoid touching
   `MissionService`'s construction beyond the one bug fix in scope.
5. External channels (SMTP/SMS/WhatsApp/CAP) untouched, per explicit
   instruction.

## 13. Tests

- `tests/unit/test_alert_lifecycle.py` — 10 tests: creation, no-op on empty
  deliveries, correlation/dedup, authorized/unauthorized transitions
  (including SYSTEM principal denial), illegal transitions, audit trail.
- `tests/api/test_alert_lifecycle_endpoint.py` — 6 tests: CASE-VALID replay
  produces exactly one listable alert, 403 on unauthorized acknowledge with
  state left unchanged, full acknowledge→escalate→resolve lifecycle via the
  real API, 404 on unknown alert, and the mission-audit persistence
  regression.
- Full backend regression: **780 passed, 10 skipped, 1 pre-existing failure**
  (`test_netra_training_loop`, unrelated — unchanged from baseline). Baseline
  before this task: 766/10/1. +14 new tests (net after accounting for a
  fixed helper), zero regressions.
- Frontend: `npx tsc --noEmit` 0 errors, `npm run build` succeeds (14/14
  routes), `npm run test` 11/11 passing (unchanged — this task did not add
  new frontend unit tests; the new pages were verified live via HTTP/curl
  and the browser dev server instead).

## 14. Browser / live verification

Backend restarted to load this task's changes; frontend dev server left
running (hot-reloading Next.js/Turbopack). Verified live via `curl` against
`http://127.0.0.1:8000`:

1. `GET /v1/replay/CASE-VALID` → 200, `alerts` section populated.
2. `GET /v1/cases/REPLAY-CASE-VALID/alerts` → 200, exactly one
   `AlertRecord`, `status: "created"`.
3. Unauthenticated `POST /v1/alerts/{id}/acknowledge` → 401 (no fake
   mutation).
4. Unauthenticated `POST /v1/missions/{id}/approve` → 401.
5. `frontend` dev server responding 200 at `http://localhost:3000/`.
6. `GET /v1/replay/CASE-OOD` → 200, `GET /v1/cases/REPLAY-CASE-OOD/alerts` →
   `{"items": []}` — the negative/fail-closed case (Phase 14): a case that
   never reaches a decision correctly produces zero `AlertRecord`s, because
   `check_materiality()` withholds the send before `sync_from_deliveries()`
   ever sees a deliverable result. No alert is fabricated for a case with
   insufficient evidence.

Full interactive browser click-through (opening `/alerts` and `/missions` in
an actual browser window and clicking Acknowledge/Approve) was **not
performed** — no browser-automation tool was available in this environment,
matching the pattern already established and disclosed in the STEP4/5
reports. All available HTTP/build/type/test verification was completed.

## Definition of Done

- [x] Alert generation connected to real material state changes (unchanged, pre-existing — `validity.evaluated` only)
- [x] Severity is real
- [x] Deduplication is real (correlation via `sync_from_deliveries`)
- [x] Role routing is real (unchanged, pre-existing)
- [x] Alert lifecycle is real (new this task)
- [x] Alerts visible in frontend
- [x] Alert reason/evidence linkage visible
- [x] Mission state visible
- [x] Mission authorization is backend-authoritative (pre-existing, verified)
- [x] Unauthorized users cannot mutate mission state (verified live)
- [x] PRAMAN/audit captures alert correlation; mission audit answerable via new endpoint
- [x] REAL/REPLAY/SIMULATED remain distinct
- [x] No fake alert delivery
- [x] No fake mission approval
- [x] CASE-VALID demonstrates the alert/operational path
- [x] Negative/fail-closed case (CASE-OOD) — live-verified: zero `AlertRecord`s created
- [x] TypeScript passes
- [x] Frontend build passes
- [x] Frontend tests pass
- [x] Backend regression remains clean
- [x] Local stack works
- [x] Browser/manual verification performed where possible (HTTP-level; interactive click-through not available)

STOP per instruction — not continuing into live-data orchestration, benchmark, NETRA training, learned CHHAYA/SMRITI, or further frontend redesign.
