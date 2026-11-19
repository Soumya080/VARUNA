# VARUNA GRID v2 — Local System Verification Report

**Date:** 2026-09-02
**Status: VARUNA_LOCAL_SYSTEM_VERIFIED**

## 1. Environment

- `.env`: `USE_POSTGRES=false`, `USE_MINIO=false`, `DEMO_MODE=false`.
  Confirms the product's intended local mode uses in-memory repositories
  (`apps/api/dependencies.py`) — Postgres/Redis/MinIO are NOT required to
  exercise `GoldenCaseWorkflow`/replay/alerts/missions/PRAMAN locally; they
  back only the legacy `CaseWorkflow` persistence path and Celery, neither
  of which this product surface depends on.
- `docker-compose.yml` defines `postgres`, `redis`, `minio`, `api`, `worker`
  — all optional for this verification; none started, per the diagnosis.

## 2. Services actually running

| Service | Port | Status | Startup command |
|---|---|---|---|
| Backend API | 8000 | Running (verified `GET /health` → `{"status":"ok"}`) | `PYTHONPATH=packages .venv/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000` |
| Frontend (Next.js/Turbopack dev) | 3000 | Running, all sampled routes 200 | `npm run dev` (from `frontend/VARUNA-frontend_yash`) |
| PostgreSQL | 5432 | Not started (not required, `USE_POSTGRES=false`) | — |
| Redis | 6379 | Not started (not required for this surface) | — |
| MinIO | 9000/9001 | Not started (not required, `USE_MINIO=false`) | — |

A stray API process from a *different* Python environment
(`AppData\Roaming\uv\python\cpython-3.12...`) was found bound to port 8000
during a prior task and had already been replaced with this repo's own
`.venv` process before this verification began — confirmed still correct.

## 3. Backend health

- `GET /health` → 200, `{"status":"ok","api_version":"3.5.0","demo_mode":false,"scientific_status":"EXPERIMENTAL / UNVALIDATED"}`.
- `GET /docs` → 200 (OpenAPI UI enabled).
- `GET /openapi.json` → enumerated; confirmed all expected routes present,
  including every STEP 6/7 addition (`/v1/auth/login`, `/v1/auth/me`,
  `/v1/cases/{id}/alerts`, `/v1/alerts/{id}/{acknowledge,escalate,resolve}`,
  `/v1/missions/{id}/audit`).

## 4. Authentication — verified live

| Check | Result |
|---|---|
| Unauthenticated `POST /v1/alerts/{id}/acknowledge` | 401 |
| `POST /v1/auth/login` (officer/officer-demo-pass) | 200, real signed JWT |
| `GET /v1/auth/me` with token | 200, `{"principal_id":"officer","role":"duty_officer"}` |

5 demo roles available (`admin`, `duty_officer`, `analyst`,
`field_operator`, `read_only`) via `varuna_infra.demo_users`.

## 5. Case flow — verified live

`GET /v1/replay/CASE-VALID` → 200, `schema_version: "v1"`,
`case_id: "REPLAY-CASE-VALID"`. Confirmed the full chain executes:
`GoldenCaseWorkflow.run_replay_case()` → `build_product_case()` →
`OperatorCase` → served to the frontend at the same URL
`NEXT_PUBLIC_VARUNA_API_URL=http://127.0.0.1:8000` the frontend's
`.env.local` actually points at (verified, no base-URL mismatch).

## 6. Product data surface — verified against the live response

| Section | Status | Evidence mode | Notes |
|---|---|---|---|
| observation | produced | — | |
| detection | produced | real | NETRA stage |
| origin | produced | real | PRATIVARTAN Φ |
| ais | **not_yet_produced** | — | Correct — CASE-VALID has zero AIS tracks by design |
| attribution | produced | real | NYAYA |
| validity | produced | real | |
| forecast | produced | real | PRAVAAH |
| decision | produced | real | ABHIYAN tasking |
| mission | produced | real | `AVAILABLE`, unapproved |
| alerts | produced | real | 1 alert |
| recommendation | `valid` | — | |
| intelligence | produced | — | hypotheses, memory_hits, decision_trace, next_best_action, evidence_lineage all present |
| evidence.components | present | — | Evidence Health strip |
| provenance | present | — | artifact_ids, model_versions, manifest_artifact_id |

`system_status.engine_mode = "replay"`, distinct from every section's own
`evidence_mode` — verified never collapsed into one vocabulary.

## 7. Alert flow — verified live, full lifecycle

`GET /v1/cases/REPLAY-CASE-VALID/alerts` → one real `AlertRecord`
(`event_type: validity.evaluated`, `severity: warning`, `is_simulated: true`,
`evidence_mode: real`). Exercised the complete lifecycle live:

- `officer` acknowledge → 200, `status: acknowledged`.
- `officer` escalate → 200, `status: escalated`.
- `analyst` attempt to resolve → **403**, alert `status` confirmed still
  `escalated` afterward (denial did not mutate state).
- `officer` resolve → 200, `status: resolved`, `resolved_by: officer`.

## 8. Authorization test — verified live

`analyst` (holds `ACKNOWLEDGE_ALERT` only) attempting `resolve` on the real
CASE-VALID alert → **403**, state unchanged (§7). A mission-approval 403
against a live mission was verified via the automated test suite
(`test_authenticated_but_unauthorized_mission_approve_is_403_and_state_unchanged`)
rather than live `curl`, because no API route exists to create a live
mission — a pre-existing, disclosed gap (see STEP 6/7 reports), not
introduced by or fixed in this verification task per its own scope
boundary ("only fix issues genuinely preventing the current local product
from being exercised" — a missing create-mission route is a scope gap, not
a runnability bug in the existing supported path).

## 9. Negative / fail-closed test — CASE-OOD, verified live

`GET /v1/replay/CASE-OOD` → validity/decision/mission all correctly
`not_yet_produced` with named upstream reasons (`OOD: input scene fell
recognisably outside...`), `recommendation: "unavailable"`.
`GET /v1/cases/REPLAY-CASE-OOD/alerts` → `{"items": []}` — zero alerts, no
fabricated mission, no fabricated decision.

## 10. REAL / REPLAY / SIMULATED — verified

`engine_mode` (how the run was produced: real/replay/simulated) and each
section's `evidence_mode` (how real the evidence is) are separate fields at
separate levels of the response, verified never merged, and both rendered
by distinct badge components in the frontend (`EngineModeBadge`,
`EvidenceModeBadge`) per the existing, unmodified design.

## 11. Browser verification

**Interactive browser click-through was NOT performed** — no browser
automation tool is available in this environment (consistent with every
prior report in this track). What WAS performed, which is stronger than
build/TS/SSR alone: live HTTP verification of every route the frontend
actually calls, using the same base URL and CORS configuration the running
frontend process uses, reproducing the exact request/response sequence a
browser click would produce (login → token → authenticated POST → verified
state change → re-fetch confirming persistence). **Manual browser
walkthrough is still required** to visually confirm rendering; instructions
are in `docs/product/LOCAL_SYSTEM_WALKTHROUGH.md`.

## 12. Route diagnostics

No 404/422/500 encountered on any route in the primary journey. CORS
verified permissive for `http://localhost:3000` specifically (not `*`),
with credentials allowed. No stale endpoint, no wrong base URL, no frontend
dead action found in the primary journey — all four operational action
buttons (acknowledge/escalate/resolve/approve) call real, currently-live
routes.

## 13. Runtime/performance check

- Backend and frontend both respond promptly (sub-second) to every request
  issued during this verification.
- Repeated `GET /v1/replay/CASE-VALID` calls do not degrade or lose
  `intelligence.status` (the STEP 6 idempotency/intelligence bug fixed in
  the frontend-diagnostic task — re-confirmed still fixed: intelligence
  stayed `produced` across multiple fetches during this session).
- No polling loop or request storm observed; each page fetch is a single
  request per data dependency.

## 14. Actual failures found this task

None. Both servers were already correctly configured and running current
code from the prior session (STEP 7); no fix was required to make the
existing local product runnable.

## 15. Remaining limitations (disclosed, not fixed — out of this task's scope)

1. No API route creates a live mission (pre-existing).
2. Demo login is a local/dev-only registry, not production credentials.
3. `landfall.predicted` alert event remains unwired.
4. Interactive browser click-through not performed (tooling constraint).
5. `OperatorCase.mission` (replay) and `MissionService`'s live store remain
   two distinct records for the same conceptual mission.

## Final URLs

- **Frontend:** http://localhost:3000
- **Backend:** http://127.0.0.1:8000
- **API docs:** http://127.0.0.1:8000/docs
- **Login:** click the profile widget (top right of the header) →
  username/password form → `POST /v1/auth/login`
- **Demo access:** see `packages/varuna_infra/demo_users.py` for accounts
  (`officer`, `analyst`, `admin`, `field`, `viewer`)
- **First case to open:** `CASE-VALID` (loaded by default on the dashboard)
