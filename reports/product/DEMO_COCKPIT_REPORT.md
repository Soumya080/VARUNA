# VARUNA — Final Demo Cockpit

**Date:** 2026-09-02
**Verification:** real Chromium (Playwright) driving the running stack through the full operator story and the fail-closed story.

---

## 1. Exact files changed

**Backend**
| File | Change |
|---|---|
| `apps/api/routers/run_stream.py` *(new)* | SSE execution stream — `GET /v1/run/{fixture}/stream`, `GET /v1/run/fixtures` |
| `apps/api/main.py` | registered `run_stream.router` |
| `packages/varuna_domain/golden_case_engine.py` | `_sync_missions_to_service()` — registers the run's own `MissionRecord` with `MissionService` so the real approve route can address it |

**Frontend**
| File | Change |
|---|---|
| `app/page.tsx` | **rewritten** as the canonical Mission Cockpit (zero mock-data) |
| `components/cockpit/case-map.tsx` *(new)* | real Leaflet map driven by OperatorCase geometry |
| `components/cockpit/cockpit-panels.tsx` *(new)* | timeline + evidence panels, all from OperatorCase |
| `lib/use-run-stream.ts` *(new)* | EventSource consumer for the SSE stage stream |
| `lib/operator-case-types.ts` | added `BBoxValue`; typed `SlickDetectionValue.bbox`; **removed** `allows_operational_action` (never serialised — see §11) |
| `package.json` | `leaflet`, `react-leaflet`, `@types/leaflet` |

**Tooling** — `scripts/cockpit_acceptance.py` *(new)*, real-browser acceptance harness.

## 2. Exact map implementation

**Leaflet + react-leaflet** with **OpenStreetMap** raster tiles (verified reachable from this machine; no tile server, no API key, no new infrastructure). Rendered client-only via `next/dynamic({ ssr:false })` because Leaflet touches `window` at import.

There is **not one hardcoded coordinate, centre or zoom** in `case-map.tsx`. The viewport is computed by collecting every real coordinate the case carries — starting point, detection centroid, detection bbox corners, Φ bbox corners, landfall positions — and calling `map.fitBounds()` over their union. CASE-VALID opens over the Gulf of Mexico solely because its detection centroid is at `-88.970, 28.936`. **No data was moved to make the map look right.**

Layers, each rendered only when the backend actually produced it:

| Layer | Source | CASE-VALID |
|---|---|---|
| Basemap | OSM tiles | ✔ 12 tiles rendered |
| NETRA detection footprint | `detection.value.bbox` | ✔ orange rectangle |
| PRATIVARTAN Φ support | `origin.value.bbox` | ✔ blue dashed rectangle |
| Starting point | `starting_point.point` | ✔ red marker |
| PRAVAAH landfall | `forecast.value.landfalls[].position` | ✔ green marker |
| PRAVAAH forward reach | start → landfall segment | ✔ dashed, **popup states it is not a modelled drift path** |
| AIS tracks | `ais.value` | not produced for this fixture (honest) |

**Trajectory honesty:** `ForwardForecast` carries `trajectory_path` (a `.npz` reference), not vertices, and `PhiField` carries a bbox + `spatial_modes`, not a polyline. No drift curve is synthesised. The forward segment is drawn dashed and its popup says explicitly: *"Not a modelled drift path — the contract supplies a trajectory file reference, not vertices."*

**Map vs. science separation (§3 of the brief):** the basemap coastline is never used as a land classifier. The map legend shows `LAND MASK UNKNOWN / NOT AVAILABLE`, mirroring the backend's `land_classification = unknown_no_landmask`. `REJECTED_LAND` remains implemented and will engage unchanged when a real mask exists.

## 3. Exact backend event/run implementation

`GET /v1/run/{fixture}/stream` — plain FastAPI `StreamingResponse` over `text/event-stream`. No Kafka, Celery, Redis, or new services. It executes the same canonical path everything else uses:

```
GoldenCaseWorkflow.run_replay_case(force=True) -> build_product_case() -> OperatorCase
```

Event types: `run_started`, `stage` (×13), `run_complete`, `run_failed`. Stages:
`DATA, NETRA, DETECTION_EVIDENCE, STARTING_POINT, PRATIVARTAN, PRAVAAH, CHHAYA, NYAYA, VALIDITY, NEXT_BEST_ACTION, ALERT, MISSION, PRAMAN`.

Each `stage` event carries `stage`, `status`, `elapsed_ms`, `stage_runtime_ms`, `reason`, `case_id`, `run_id`, `detail`.

**Progress honesty — stated precisely, because "do not fake progress" is a hard requirement:**
- `elapsed_ms` is always real monotonic wall-clock from run start. **No artificial delay is ever inserted.**
- `status` is the real `StageResult.status` / section `ProducerStatus` — never a hardcoded success list.
- `stage_runtime_ms` is the producer's own recorded runtime, and **`null` when it recorded none**. Replay fixtures are canned data and record no per-stage runtime, so it is `null` — reported honestly rather than back-filled.
- Because `run_replay_case()` is one synchronous call returning a fully-populated run, its pipeline stages genuinely all become observable at the same instant, so their `elapsed_ms` values cluster (~25 ms) and the two compose-derived stages land later (~28 ms). **The stream does not spread them out to look more impressive.** That clustering is the truth about how a replay executes.

## 4. Canonical cockpit route

**`/`** — `app/page.tsx`. Layout as specified: LEFT execution timeline · CENTER real map + starting point · RIGHT evidence/intelligence · BOTTOM recommended action / alert / mission / PRAMAN. Header carries the OBSERVE → DETECT → LOCALIZE → FORECAST → ATTRIBUTE → ASSESS → RECOMMEND → AUTHORIZE → RECORD story strip, engine-mode badge and case id. Scenario selector: CASE-VALID / CASE-OOD / CASE-SIMULATED.

Everything on it describes **one** case/run from a single `OperatorCase`.

## 5. Mock-data dependencies removed from the canonical path

`grep -rn "mock-data" app/page.tsx components/cockpit/ lib/use-run-stream.ts lib/operator-case-context.tsx` → **only two comment lines** saying the files import none. Zero real imports.

Removed from `/`: `MAP_BOUNDS`, `ORIGIN`, `SLICK_INFO`, `VESSELS`, `project()`, `CASE_SUMMARY`, `PIPELINE`, `RECOMMENDED_ACTION`, `MISSION_STATES`, `CURRENT_MISSION_STATE`, the static `arabian-sea-satellite.png` basemap, and the legacy `case-intelligence` / `analytical-pipeline` / `mission-status` / `case-summary` mock-backed components. Legacy pages still import `mock-data` but no longer contaminate `/`.

## 6. Real Chromium walkthrough result

Executed against the running stack (`scripts/cockpit_acceptance.py`):

| # | Step | Result |
|---|---|---|
| 1-2 | Login `officer` | ✔ `OF \| officer \| Duty Officer` |
| 3-4 | RUN VARUNA, watch stages | ✔ all 13 stages streamed and lit: Data/forcing, NETRA, Detection evidence, Starting point, PRATIVARTAN (Φ), PRAVAAH, CHHAYA, NYAYA, Validity gate, Next best action, Alert, Mission, PRAMAN |
| 5 | Map over Gulf of Mexico | ✔ 12 OSM tiles, 5 vector layers, OSM attribution present |
| 6 | Detection geometry | ✔ rectangle from real `detection.bbox` |
| 7 | Starting point | ✔ `28.936° N \| 88.970° W \| detection centroid \| AVAILABLE` |
| 8 | Backward reconstruction | ✔ Φ bbox rendered (no fabricated polyline) |
| 9 | Forward forecast | ✔ landfall marker + labelled reach segment |
| 10 | Evidence/intelligence | ✔ classification, confidence, OOD risk, top hypothesis, posterior, **"CHHAYA is uncalibrated"** disclosure, NYAYA top posterior |
| 11 | Validity | ✔ `VALID` / operational action **allowed** |
| 12 | Recommendation | ✔ `valid` + gate reasoning |
| 13 | Alert | ✔ `CREATED`, severity from backend |
| 14 | Acknowledge alert | ✔ **"Alert acknowledged — confirmed by backend."** |
| 15 | Authorize mission | ✔ **"Mission authorized — confirmed by backend."** → state `assigned`, `human_approved_by: officer` |
| 16 | PRAMAN | ✔ case, run, artifacts, actor, generated-at |
| 17 | Logout | ✔ `Not signed in`, localStorage cleared |
| 18 | Login `analyst` | ✔ `AN \| analyst \| Analyst` |
| 19-20 | CASE-OOD | ✔ `STARTING_POINT_UNAVAILABLE` with named reason, "NO GEOGRAPHIC EVIDENCE FOR THIS CASE", recommendation `unavailable`, **"No alert for this case… no alert is fabricated"**, no mission |

**Network: zero failed requests.** The only non-200 was a deliberate re-approval of an already-`ASSIGNED` mission → `400 illegal mission transition assigned -> assigned`, which is the FSM correctly refusing a duplicate — confirmed by the audit trail showing the genuine prior approval.

## 7-9. Access

| | |
|---|---|
| **Frontend** | http://localhost:3000 |
| **Backend** | http://127.0.0.1:8000 |
| **API docs** | http://127.0.0.1:8000/docs |
| **Login** | profile widget (top-right) → `officer` / `officer-demo-pass` |
| **First action** | scenario `CASE-VALID` → **Run VARUNA** |

## 10. Latency before / after

| Measurement | Before this track | Now |
|---|---|---|
| `GET /v1/replay/CASE-VALID` (repeat) | 34–54 ms | **3.0–3.2 ms** (cached) |
| Explicit `?refresh=true` | n/a | 29.5 ms |
| Full SSE run (workflow + compose) | 614 ms cold, uninstrumented | **28.6 ms** (workflow 25.1 + compose 1.1) |

Composed-response cache preserved; `force=true` is **not** restored as a default — first request executes for real, repeats are cached, `?refresh=true` recomputes.

## 10b. Regression

**Backend: 809 passed, 10 skipped, 1 pre-existing unrelated failure**
(`test_netra_training_loop`) — identical to the pre-task baseline, zero
regressions. Frontend: `tsc --noEmit` 0 errors, `npm run build` 14/14 routes.

## 11. Bug found and fixed during this work

`ValidityGateResultValue.allows_operational_action` was still **declared** in TypeScript as `boolean` even though it is a Python `@property` on the `ValidityState` enum and is never serialised. Any future component reading it would have silently reproduced the STEP-7 "VALID / does not allow operational action" contradiction. The field is now **removed from the type** with a comment directing callers to derive it from `state`, so the bug cannot recur by accident.

Also: the replay fixture's `MissionRecord` was built directly and never registered with `MissionService`, so `POST /v1/missions/{id}/approve` returned **404** — mission authorization was unreachable from any UI. `_sync_missions_to_service()` now registers the run's own record. It never sets `human_approved_by` and never advances state; approval still requires `authorize()` and a real human principal.

## 12. Remaining demo blockers / limitations

1. **No land mask.** `land_classification` is honestly `unknown_no_landmask` and the UI says `LAND MASK UNKNOWN / NOT AVAILABLE`. `REJECTED_LAND` is implemented and compatible.
2. **No real trajectory polylines.** The contract exposes a `.npz` path, not vertices, so PRATIVARTAN/PRAVAAH are shown as extent + endpoints, with the limitation stated in the map popup. Exposing real vertices is a backend contract change, not a frontend fix.
3. **9 legacy pages remain mock** (`/cases`, `/detection`, `/source-reconstruction`, `/vessel-attribution`, `/intelligence`, `/evidence-chain`, `/assets`, `/reports`, `/assignment-mission`). They no longer contaminate `/`. The left nav and case-rail still show mock case names on those pages.
4. **Replay stages are not individually timed** — canned fixtures record no per-stage runtime, so `stage_runtime_ms` is `null` and stage `elapsed_ms` values cluster. A real (non-replay) run through `RealE2EPipeline` does record per-stage runtimes.
5. **Alert lifecycle is process-lifetime state.** Re-running CASE-VALID does not reset an already-acknowledged alert (correct by design), so a repeat demo shows the alert in its retained state; restart the API for a pristine run.
6. **OSM tiles require internet.** Verified reachable here; an offline demo would show the vector layers over an empty basemap.
7. **CASE-SIMULATED** is selectable and clearly labelled by the engine-mode badge, but was not click-verified in this Chromium pass (CASE-VALID and CASE-OOD were).
