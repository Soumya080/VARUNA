# VARUNA GRID v2 — Real Authentication + Complete Operational Action Path

**Task:** Integration Track STEP 7
**Date:** 2026-09-02

## Final status: **AUTH_OPERATIONAL_VERIFIED**

---

## 1. Diagnosis (Phase 0)

Inspected before building anything:

- `varuna_infra/auth.py` — `create_access_token()`/`verify_token()` already
  existed, fully functional (real HS256 signing, real expiry), but had
  **zero production callers**. Only `tests/unit/test_api_security.py`
  exercised it.
- `apps/api/security.py::get_principal` — already the single, correct
  identity-resolution boundary: verifies a real `Bearer` JWT, or (only when
  `settings.demo_mode=True`) accepts unsigned `X-User-Id`/`X-User-Role`
  headers. `demo_mode` is `false` in `.env`. Already used by every
  state-changing route, including the STEP 6 alert/mission endpoints.
- `apps/api/middleware/auth.py::AuthMiddleware` — a deliberate pass-through;
  enforcement correctly lives at the per-route dependency layer instead
  (documented in its own docstring), not a gap.
- **No login endpoint existed anywhere** — confirmed by exhaustive search;
  `security.py`'s own docstring already disclosed this.
- **No user registry/database existed anywhere.**
- `varuna_infra/rbac.py` — real permission table, already correctly gated
  every alert-lifecycle and mission-approval action (STEP 6).
- Frontend — **zero auth code existed**: no login page, no token storage, no
  `Authorization` header ever sent by any `fetch()` call.
- `tests/unit/test_api_security.py` already covered `get_principal()` in
  isolation thoroughly (valid JWT, wrong secret, expired, malformed header,
  demo-mode gate) — reused and extended, not duplicated.

Conclusion: the JWT *mechanism* was complete and correct; only the *login
path that mints a token* and the *frontend that uses one* were missing —
exactly the gap this task targets.

## 2. What was built

| Component | File |
|---|---|
| Demo user registry (sha256+salt, disclosed as demo-only, not bcrypt/passlib since neither was an existing dependency) | `packages/varuna_infra/demo_users.py` |
| `POST /v1/auth/login`, `GET /v1/auth/me` | `apps/api/routers/auth.py` |
| `access_token_expire_minutes` setting (30 min) | `apps/api/config.py` |
| `AuthProvider` React context — session in `localStorage` for this browser's convenience only, never trusted by the backend | `frontend/.../lib/auth-context.tsx` |
| `login()` client fn, shared token holder attached to every POST call, `AuthActionError` | `frontend/.../lib/api.ts` |
| Real login/logout widget replacing the hardcoded "Analyst Rao" identity | `frontend/.../components/header.tsx` |
| 401-vs-403 (NOT AUTHENTICATED vs NOT AUTHORIZED) distinction + real success confirmation on every action button | `alerts/page.tsx`, `mission-status.tsx`, `missions/page.tsx` |
| `mission.assigned` and `attribution.generated` wired into the existing alert architecture (Phase 5) | `packages/varuna_missions/service.py`, `packages/varuna_integration/pipeline.py`, `packages/varuna_domain/golden_case_engine.py` |
| Test isolation fixture for the process-lifetime alert/mission singletons | `tests/api/conftest.py` |

No new alert store, no new mission store, no second authorization mechanism,
no change to `varuna_nyaya`/`varuna_prativartan`/`varuna_pravaah`/NETRA.

## 3. Login flow (Phase 1)

`POST /v1/auth/login {username, password}` → `varuna_infra.demo_users.authenticate()`
(constant-time hash comparison, same 401 shape for unknown user vs. wrong
password — cannot be used to enumerate accounts) → on success,
`varuna_infra.auth.create_access_token(role=<registry role>, ...)`. The
request body has **no role field** — verified by test
`test_client_cannot_supply_its_own_role`, which sends one anyway and
confirms it is ignored. Five demo accounts, one per `varuna_infra.rbac.Role`
member, credentials disclosed in the registry's own docstring (not a secret
boundary — the JWT signature is).

## 4. JWT flow (Phase 1)

Unchanged mechanism, now actually reachable: `create_access_token()` signs
with `settings.jwt_secret_key`/`jwt_algorithm`, bounded to
`access_token_expire_minutes` (30 min default). `get_principal()` verifies
signature and expiry exactly as before STEP 7 — this task added a caller,
not a new verification path.

## 5. Role model

Unchanged (`varuna_infra.rbac`), reused as-is. Every login-issued token's
role comes from the server-side registry and is checked by the exact same
`authorize()` STEP 6 already wired into alert lifecycle actions and mission
approval.

## 6. Frontend auth (Phase 2)

`AuthProvider` restores a session from `localStorage` on mount, exposes
`login()`/`logout()`/`isAuthenticated`/`isExpired`. `lib/api.ts` holds the
current token in a module-level variable (`setAuthToken`), attached as
`Authorization: Bearer <token>` to every `POST`. The header's profile widget
(previously hardcoded "Analyst Rao / Watch Officer") now shows the real
signed-in username and role, or an inline sign-in form when not
authenticated — same visual position and footprint, no redesign.

## 7. Operational actions (Phase 3)

All four verified end-to-end through the real chain (frontend action → API
→ JWT validation → principal → RBAC → state mutation → audit): acknowledge,
escalate, resolve (STEP 6), approve mission (pre-existing, now reachable
from a real login). No button optimistically updates local state before the
backend confirms — every handler applies the response object, or shows an
error, never an assumed success.

## 8. Authorization test matrix (Phase 4)

`tests/api/test_auth_operational_matrix.py` (12 tests), all against the
**real** `/v1/auth/login`-issued tokens, not `dependency_overrides`:

- Unauthenticated acknowledge/approve → 401.
- Authenticated-but-unauthorized (`read_only` acknowledge, `analyst`
  mission-approve) → 403, state verified unchanged afterward.
- Authorized role (`duty_officer`) → success, response confirms new state.
- `analyst` can acknowledge but not escalate (role-scoped permissions).
- System-principal-style token (`role=system`) → 403 on mission approval,
  re-verifying the pre-existing policy through the full JWT path.
- Denied mission approval leaves `state=available`,
  `human_approved_by=null`.
- Successful approval is audited (`GET /v1/missions/{id}/audit` shows the
  ALLOWED entry for the real principal).
- Expired token, malformed token, and a tampered (bit-mangled) token all →
  401, never 500.

## 9. Remaining alert event wiring (Phase 5)

Two previously-dead-code material event types are now genuinely wired,
reusing the existing `varuna_alerts` architecture with no second alert
pathway:

- **`attribution.generated`** — `RealE2EPipeline._alerts()` now also emits
  this event at the same call site as `validity.evaluated`, gated by the
  SAME case `ValidityState` (no separate/fabricated materiality judgment).
  `StageResult.detail["events"]` groups each event's own delivery results;
  `GoldenCaseWorkflow._sync_alerts_to_lifecycle()` correlates each group
  into its own `AlertRecord`. The pre-existing aggregate `detail` keys
  (`n_actually_delivered`, `delivery_claim`, ...) stay computed across all
  events combined, preserving `test_alerts_never_claim_undelivered_delivery`.
- **`mission.assigned`** — fired from `MissionService.approve_and_assign()`
  itself (the only place a mission genuinely becomes ASSIGNED; the pipeline
  never assigns one). Uses `gate_state=ValidityState.VALID` deliberately: by
  the time this fires, `authorize()` has already required and verified a
  real human's `APPROVE_MISSION` permission — a stronger, more specific gate
  than case evidence-validity, which `MissionService` has no access to.
  Live-verified: `test_mission_assigned_alert_is_raised_on_real_approval`
  confirms the alert appears via `GET /v1/cases/{case_id}/alerts`
  immediately after a real approval.

`landfall.predicted` remains unwired, documented as a deliberate
non-fabrication: doing so honestly would require a proximity-to-shore
threshold policy that does not exist anywhere in this repository — the
same category of invented safety-critical rule `varuna_alerts/severity.py`
already refuses to fabricate for CRITICAL severity.

## 10. PRAMAN / audit (Phase 6)

- Alert correlation (creation of each `AlertRecord`, including the two
  newly-wired event types) is registered as a PRAMAN artifact via
  `GoldenCaseWorkflow._sync_alerts_to_lifecycle()` (STEP 6, unchanged
  mechanism, now covering more event types).
- Mission approval/denial is recorded in `MissionService.audit_log`
  (persistent singleton, STEP 6 fix) and answerable via
  `GET /v1/missions/{id}/audit` — actor, role, permission, operation,
  allowed/denied, subject, timestamp. No secret (token, password) is ever
  written to any audit entry — verified by inspection of `AuditEntry`'s
  fields, which carry only `principal_id`/`role`/`permission`/`operation`.

## 11. Browser / live E2E (Phase 7)

Backend restarted (a stale process from a different Python environment was
found bound to port 8000 serving pre-STEP-7 code — verified via its real
command line before stopping it, same care as the STEP 6 diagnostic) so the
new routes were actually live. Verified via `curl` against
`http://127.0.0.1:8000`:

1. `POST /v1/auth/login` (officer) → real signed JWT.
2. `GET /v1/replay/CASE-VALID` → 200.
3. `GET /v1/cases/REPLAY-CASE-VALID/alerts` → one alert, `status: created`.
4. `POST /v1/alerts/{id}/acknowledge` with the real token → 200,
   `acknowledged_by: "officer"`.
5. `GET /v1/alerts/{id}` → confirms the persisted state change.
6. `POST /v1/alerts/{id}/escalate` with the same token → 200,
   `status: escalated`.
7. Malformed token (`Bearer not-a-real-jwt`) → 401.
8. Tampered token (valid JWT with mangled trailing characters) → 401.
9. Frontend dev server responds 200 at `/`, `/alerts`, `/missions`.

Mission-approval + audit was verified through the automated integration
test (`test_authorized_duty_officer_approves_mission_and_it_is_audited`,
real HTTP call, real JWT, same singleton the live server uses) rather than
live `curl`, because **no API route exists to create a mission** — only
`GET`/`approve`/`audit` are exposed (a pre-existing gap, not introduced or
in scope to fix here; `MissionService.create_mission()` is only ever called
internally). This is disclosed, not silently substituted.

**Interactive browser click-through was not performed** — no browser
automation tool is available in this environment, matching the disclosed
limitation in the STEP4/5/6 reports. All available HTTP, build, type, and
automated test verification was completed instead.

## 12. Frontend honest state (Phase 8)

Every action button distinguishes: not signed in (inline prompt, action
buttons hidden or disabled), signed in, NOT AUTHORIZED (403, role-specific
message), NOT AUTHENTICATED (401 — triggers an automatic `logout()` so a
stale/expired token cannot linger silently), and success (backend response
applied to local state, explicit confirmation text). No handler ever
applies an optimistic update before the backend responds.

## 13. Tests

- `tests/api/test_auth_login.py` — 7 tests (valid login, wrong password,
  unknown-username same-shape 401, role cannot be client-supplied, all 5
  demo accounts log in, `/me` without token, `/me` with tampered token).
- `tests/api/test_auth_operational_matrix.py` — 12 tests (full matrix, §8).
- `tests/api/conftest.py` — new isolation fixture (no test count, but
  fixes real cross-test-file state bleed the new tests exposed).
- `frontend/.../lib/__tests__/auth-error-classification.test.ts` — 4 tests.
- Full backend regression (re-run after all Phase 5 wiring changes):
  **799 passed, 10 skipped, 1 pre-existing failure** (`test_netra_training_loop`,
  unrelated). Baseline before this task: 780/10/1 (STEP 6 final). +19 net,
  zero regressions.
- Frontend: `npx tsc --noEmit` 0 errors, `npm run build` succeeds (14/14
  routes), `npm run test` 15/15 passing.

## 14. Remaining limitations

1. Demo user registry (`varuna_infra/demo_users.py`) is explicitly not a
   production credential store — five hardcoded accounts, sha256+salt (no
   bcrypt/passlib dependency existed to justify adding one for this scope).
2. No route creates a live mission via the API — `MissionService.create_mission()`
   has no HTTP entry point, so a live mission-approval demo requires the
   automated test's direct service call rather than a pure `curl` sequence.
3. `landfall.predicted` remains unwired (§9) — would require fabricating an
   urgency/proximity policy that does not exist in this repository.
4. Interactive browser click-through not performed — no automation tool
   available; HTTP-level verification substituted throughout.
5. `OperatorCase.mission` (replay fixture) and `MissionService`'s live
   store remain two distinct records for the same conceptual mission — a
   pre-existing STEP 6 gap, unchanged by this task.

STOP per instruction — not continuing into live-data orchestration,
benchmark, NETRA training, learned CHHAYA/SMRITI, or further redesign.
