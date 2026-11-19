# VARUNA — Runtime Stabilization + Full Loop Repair

**Date:** 2026-09-02
**Verification method:** real Chromium browser (Playwright) driving the running stack, plus live HTTP and the full backend suite. Not tests alone.

---

## 1. ROOT CAUSE — auth failure

**Not reproducible on the current build; the cause was a stale server process.**

Evidence:
- `POST /v1/auth/login` with `officer` / `officer-demo-pass` returns **200** with a valid HS256 JWT (`role: duty_officer`), verified by `curl` and by a real browser.
- CORS preflight for that exact route from `Origin: http://localhost:3000` returns 200 with `access-control-allow-origin: http://localhost:3000`.
- The frontend's `.env.local` (`NEXT_PUBLIC_VARUNA_API_URL=http://127.0.0.1:8000`) was written **11 seconds before** the dev server started, so the value is correctly inlined.
- Real browser walkthrough: profile widget → `officer` → **"OF | officer | Duty Officer"**.

The actual cause, captured earlier in this session's own uvicorn log:
```
INFO: 127.0.0.1 - "POST /v1/auth/login HTTP/1.1" 404 Not Found
```
A **second uvicorn process from a different Python environment**
(`AppData\Roaming\uv\python\cpython-3.12\python.exe`) was bound to port 8000
serving code that predates the auth router. Every login therefore 404'd, and
the frontend correctly surfaced it as a failed login. Replacing it with the
repo's own `.venv` process fixes it. Nothing in the auth code was wrong, and
the documented credentials were never changed.

**Recurrence risk (real):** nothing pins which interpreter owns port 8000.
Documented in §7 as the canonical startup command.

Verified after fix: login → `GET /v1/auth/me` → logout (localStorage cleared)
→ re-login as a different role (`analyst`), all in a real browser.

## 2. ROOT CAUSE — "starting point unavailable"

**A field that does not exist was being read.**

`components/case-summary.tsx` read `oc.origin.value.centroid`. `PhiField`
carries `bbox`, `spatial_modes`, `time_distribution`, `diagnostics` — it has
**no `centroid` field at all**. The read was always `undefined`, so a
fully-`PRODUCED` origin stage rendered as:

```
RECONSTRUCTED ORIGIN
—
not produced
```

There was also no contract anywhere in the repository defining what the
starting point *is* — `grep` for `starting_point` / `release_point` found only
an unrelated `inferred_release_point` on a different schema.

**Fix — an explicit, machine-readable Starting Point Contract:**

`packages/varuna_geospatial/starting_point.py` + models in
`varuna_contracts.operator_case` (kept there because `varuna_contracts` is a
leaf package with zero `varuna_*` imports — the resolver imports the models,
not the reverse).

Sources, in precedence order, and **nothing else**:
1. `detection.value.centroid` — the validated slick centroid
2. `origin.value.bbox` centre (Phi)

Statuses: `STARTING_POINT_AVAILABLE` / `UNAVAILABLE` / `INVALID` /
`REJECTED_LAND`. There is deliberately no `DEFAULT`/`FALLBACK` source member —
an unsourced starting point is not representable by the contract.

Validation performed: finite values, geographic bounds, centroid-within-its-own-bbox,
and land classification. Live result:

| Fixture | status | source | point |
|---|---|---|---|
| CASE-VALID | `STARTING_POINT_AVAILABLE` | `detection_centroid` | `-88.970, 28.936` |
| CASE-OOD | `STARTING_POINT_UNAVAILABLE` | `none` | `null` (reason names the absence) |

Now displayed as **`STARTING POINT / 28.936° N / 88.970° W · detection centroid`**.

## 3. ROOT CAUSE — inland / land geometry

**The backend geography was correct all along. The map was 100% mock.**

- CASE-VALID's real coordinates are `lon -88.970, lat 28.936` — the MC20
  (Taylor Energy) site in the **Gulf of Mexico**, genuinely offshore. No CRS,
  axis-order, geotransform, or centroid error exists: the detection centroid
  sits inside its own bbox (`-89.02..-88.92`, `28.90..28.98`), verified.
- `components/map/map-view.tsx` imported **everything** from `lib/mock-data` —
  `MAP_BOUNDS`, `ORIGIN`, `SLICK_INFO`, `project` — and never called
  `useOperatorCaseData()`. The basemap is a **static image**
  (`/maps/arabian-sea-satellite.png`, alt text: *"Satellite imagery of the
  Arabian Sea and western coast of India"*), and `MAP_BOUNDS` is hardcoded to
  `lng 68..74, lat 15.5..21.5`.
- The "slick over land" was the hardcoded mock polygon at `18.936 N, 72.762 E`
  drawn on that Indian-coast image. Feeding the real coordinates into
  `project()` would place them at **x = -2616%, y = -124%** — entirely off the
  image, not on land.

**Fix (backend source of truth untouched — it was already right):**
`map-view.tsx` now reads `oc.starting_point` and computes whether the real
point lies inside the basemap's extent. When it does not, the satellite image
**and every Arabian-Sea-specific mock overlay** (slick, origin, particles, AIS,
wind) are hidden, and an explicit notice is shown:

> **BASEMAP DOES NOT COVER THIS CASE**
> Starting point 28.936° N 88.970° W lies outside this basemap's extent
> (15.5–21.5°N, 68–74°E). Illustrative overlays are hidden rather than drawn
> at the wrong geographic location.

The footer readout now reports the real starting point instead of the mock
origin. This is deliberately *not* "moving the marker" — it refuses to render
a case in the wrong ocean at all.

**Land mask, honestly:** the repository ships **no** offline land/coastline
mask. `geopandas` 1.1.4 removed its bundled Natural Earth dataset, and
`varuna_pravaah.coastline.check_landfall` is an India-specific latitude
heuristic (`lat > 21 → "Gujarat Coast"`) that would mislabel this Gulf of
Mexico case — so it is **not** reused. Rather than hardcode polygons and
present a guess as validation, `land_classification` returns
`unknown_no_landmask`, and the contract documents that a consumer must never
read that as "confirmed at sea". `REJECTED_LAND` exists and is enforced the
moment a real mask is supplied.

## 4. ROOT CAUSE — latency

Measured, not guessed (`scripts/measure_case_latency.py`):

| Stage | Before |
|---|---|
| `GoldenCaseWorkflow.run_replay_case(force=True)` | 614.6 ms (cold) |
| `build_product_case` (intelligence compose) | 12.1 ms |
| `GET /v1/replay/CASE-VALID` (warm process) | 34–54 ms |

Two real contributors:
1. **Every GET re-executed the entire pipeline.** `force=True` (added earlier
   to fix an idempotency bug that dropped `.intelligence`) meant
   GoldenCaseWorkflow *and* CaseIntelligenceService re-ran on every request
   for canned, deterministic replay data.
2. **The dashboard fetched CASE-VALID twice per page load** — confirmed in the
   browser network trace.

**Fix:** a composed-response cache in `apps/api/routers/replay.py`, keyed by
fixture name (bounded — 6 fixtures). It caches the **finished `OperatorCase`**,
not the intermediate `PipelineRun`: caching the run is precisely what caused
the original idempotency bug (a cached `_ReplayedRunView` has no `.stages`, so
intelligence silently vanished). Caching the composed product cannot hit that
failure mode because the intelligence is already inside it. `?refresh=true`
forces genuine re-execution.

| | After |
|---|---|
| `GET /v1/replay/CASE-VALID` #1 (cold) | 68.8 ms |
| #2 / #3 / #4 (cached) | **3.3 / 3.0 / 3.1 ms** |
| `?refresh=true` (real recompute) | 35.8 ms |

**≈11× faster** on repeat reads, `intelligence.status` still `produced`.

The duplicate dashboard fetch is React **StrictMode's dev-only** double-invoke
of `useEffect` (single provider confirmed; no nesting). It does not occur in a
production build, and disabling StrictMode would suppress a genuine dev safety
check — so it is documented rather than "fixed".

## 5. EXACT FILES CHANGED

**Backend**
- `packages/varuna_geospatial/starting_point.py` *(new)* — resolver + validation
- `packages/varuna_contracts/operator_case.py` — `StartingPoint`,
  `StartingPointStatus`, `StartingPointSource`, `LandClassification`;
  `OperatorCase.starting_point`
- `apps/api/operator_case_view.py` — resolve and attach `starting_point`
- `apps/api/routers/replay.py` — composed-response cache + `?refresh=`

**Frontend**
- `lib/operator-case-types.ts` — `StartingPoint` types
- `components/case-summary.tsx` — starting point from the contract; validity
  `allows_operational_action` derived from `state`; `formatLat/formatLng`
- `components/map/map-view.tsx` — geographic honesty guard

**Tests / tooling**
- `tests/unit/test_starting_point_contract.py` *(new, 10 tests)*
- `tests/api/conftest.py` — reset the new cache singleton
- `scripts/browser_verify.py`, `scripts/browser_dump.py`,
  `scripts/browser_walkthrough.py`, `scripts/measure_case_latency.py` *(new)*

### Additional real bug found and fixed
`components/case-summary.tsx` rendered **"VALIDITY GATE / VALID / does not
allow operational action"** — self-contradictory. `allows_operational_action`
is a Python `@property` on the `ValidityState` enum and is **never
serialised** (identical class of bug to `SourceHypothesis.top` in STEP 5); the
frontend read `undefined` and printed the negative. Now derived from `state`
exactly as the backend enum does (`VALID` or `DEGRADED`). Live-verified:
**"VALID / allows operational action"**.

Also hardened: an out-of-range upstream coordinate previously raised inside
`GeoPoint` and would have 500'd the whole operator view; the contract now
range-checks before construction and fails closed with `STARTING_POINT_INVALID`.
Found by the new test suite.

## 6. EXACT END-TO-END FLOW NOW WORKING

Verified in a real Chromium session:

```
LOGIN (officer)              -> 200, "OF | officer | Duty Officer"
  -> LOAD CASE-VALID         -> GET /v1/replay/CASE-VALID 200
  -> GoldenCaseWorkflow      -> engine_mode=replay
  -> build_product_case      -> intelligence.status=produced
  -> OperatorCase            -> all 10 stages PRODUCED (ais honestly not_yet_produced)
  -> STARTING POINT          -> 28.936 N, 88.970 W (detection_centroid)
  -> FORECAST                -> PRAVAAH panel, horizon + landfall
  -> VALIDITY                -> VALID / allows operational action
  -> ALERT                   -> validity.evaluated, severity WARNING
  -> ACKNOWLEDGE             -> 200, "Acknowledge confirmed by backend."
  -> MISSION                 -> MSN-REPLAY-REPLAY-CASE-VALID, "Not yet approved"
  -> PRAMAN / SMRITI         -> artifact ids, lineage, advisory memory panels
  -> LOGOUT                  -> "Not signed in", localStorage cleared
  -> RE-LOGIN (analyst)      -> "AN | analyst | Analyst"
```

All `/v1/` calls returned **200**; zero failed requests; zero page errors.

**Fail-closed (CASE-OOD), verified live:**
`starting_point: STARTING_POINT_UNAVAILABLE` (reason names the absence),
`recommendation: unavailable`, validity/mission/forecast `not_yet_produced`,
alerts `{"items": []}`. No fabricated coordinate, mission, or alert.

## 7. Access

| | |
|---|---|
| **Frontend** | http://localhost:3000 |
| **Backend** | http://127.0.0.1:8000 |
| **API docs** | http://127.0.0.1:8000/docs |
| **Demo login** | profile widget, top-right → `officer` / `officer-demo-pass` (registry: `packages/varuna_infra/demo_users.py`) |
| **Primary case** | `CASE-VALID` (default on the dashboard) |

**Canonical startup (pins the interpreter — prevents the §1 recurrence):**
```
# backend
cd D:\ROUTER(DATASETS)\VARUNA
PYTHONPATH=packages .venv/Scripts/python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
# frontend
cd frontend/VARUNA-frontend_yash && npm run dev
```
Postgres/Redis/MinIO are **not** required (`USE_POSTGRES=false`, `USE_MINIO=false`).

## 7b. Regression

| Suite | Result |
|---|---|
| Backend `pytest tests/ --ignore=tests/scientific` | **809 passed, 10 skipped, 1 pre-existing failure** (`test_netra_training_loop`, unrelated) |
| Baseline before this task | 799 / 10 / 1 |
| Net | **+10 tests, zero regressions** |
| Frontend `npx tsc --noEmit` | 0 errors |
| Frontend `npm run build` | success, 14/14 routes |
| Frontend `npm run test` | 15/15 passed |

One intermediate failure was caused by this task's own cache and then fixed
rather than worked around: the composed-response cache made
`GET /v1/replay/...` skip `run_replay_case()`, which is what syncs a run's
alerts into the alert store — so 9 API tests saw an empty store. The cache is
a process-lifetime singleton in the same family as the others, so it was added
to the existing `tests/api/conftest.py` isolation fixture. No test was weakened.

## 8. REMAINING BLOCKERS / LIMITATIONS

1. **No land mask** — `land_classification` is honestly `unknown_no_landmask`.
   `REJECTED_LAND` is implemented and will engage the moment a real mask is
   supplied. This is the one item that genuinely limits the geospatial
   guarantee, and it is disclosed rather than faked.
2. **9 of 12 frontend pages are still mock** (`/cases`, `/detection`,
   `/source-reconstruction`, `/vessel-attribution`, `/intelligence`,
   `/evidence-chain`, `/assets`, `/reports`, `/assignment-mission`). Only
   `/`, `/alerts`, `/missions` are backend-driven. The left case rail and the
   "ARABIAN SEA" / "24-071" header labels on the dashboard are still mock
   strings. Wiring them is frontend scope explicitly excluded from this task.
3. **No API route creates a live mission**, so Mission Control's live panel is
   honestly empty (pre-existing).
4. **React duplicate-key dev warning** on the dashboard — traced only into
   React's internal warning frame (`node_modules/next/dist/...`), not to a
   component. Dev-only, non-breaking; not chased further within this task.
5. **`varuna_pravaah.coastline.check_landfall` is India-hardcoded** and would
   emit nonsense landfalls for non-Indian basins. Not triggered by CASE-VALID
   (its forecast is a fixture), but a real hazard for real Gulf-of-Mexico runs.
6. Replay cache is per-process and in-memory (consistent with the rest of the
   local stack).
