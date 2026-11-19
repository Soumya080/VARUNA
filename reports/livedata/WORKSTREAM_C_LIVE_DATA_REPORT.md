# VARUNA GRID v2 — Workstream C: Live Data Integration

**Scope note, stated up front:** given the size of the requested workstream
(12 phases: provider interfaces, all four providers, Data Guard, normalized
artifacts, provenance, cache, GoldenCaseWorkflow wiring, mode semantics,
on-demand-only, frontend, testing) and this session's constrained budget,
this pass did **reconnaissance across all 12 phases** but only **implemented
and tested the one genuinely missing piece it found** (Sentinel-1). Every
other phase's actual status — mostly "already real, done in an earlier
session" — is reported below from direct code inspection and live
execution, not assumed. Nothing was rewritten just to look more complete.

## Phase-by-phase status (verified by reading + running, not doc alone)

| Phase | Status | Evidence |
|---|---|---|
| 1. Provider interfaces | **ALREADY DONE** | `varuna_source_adapters/protocol.py`: `SourceAdapter` ABC (`fetch`/`health_check`/`source_id`), `SourceQuery`, `FetchResult`, `evidence_mode_of()`, `fetch_with_mode()` — all pre-existing |
| 2. Sentinel-1 | **IMPLEMENTED THIS SESSION** | See below |
| 3. AIS | **ALREADY DONE** | `varuna_source_adapters/ais.py` re-exports `varuna_integration.ais_source.EventAISAdapter` — real, reads real AIS bronze/tracks, `AISJoinStatus` semantics, already wired into `RealE2EPipeline` |
| 4. ERA5 / CMEMS | **ALREADY DONE (local-file mode)** | `era5.py`/`copernicus_marine.py` — real adapters reading local GRIB/NetCDF, `is_simulated=False`, feed `PRATIVARTAN`/`PRAVAAH` via existing `ForcingCube`. Live CDS/Copernicus Marine API fetch is explicitly NOT implemented (documented in both files' own docstrings) — reading what's already on disk, honestly, not a live remote fetch |
| 5. Data Guard | **PARTIALLY DONE, not extended this session** | `varuna_data_guard.guard.evaluate_data_guard()` exists and is wired into the legacy `CaseWorkflow.ingest()` path; it validates slick-point/track shape, not yet the four provider artifacts' own metadata (SAR polarization, AIS coordinate bounds, ERA5/CMEMS coverage). Not extended in this pass — see Gaps |
| 6. Normalized artifacts | **PARTIALLY DONE** | `ForcingCube` (ERA5/CMEMS) already carries `time_series_status`/`spatial_coverage_status`; `FetchResult` carries `provenance`/`is_simulated`/`fetched_at` for all four. No single unified "NormalizedArtifact" contract spans all four sources — each has its own shape today. Not unified this session (see Gaps) |
| 7. Provenance | **ALREADY DONE** | Every adapter above returns a real `Provenance` (source_id, source_version, notes); `evidence_mode_of()`/`fetch_with_mode()` is the single translation point (ADR-0006) |
| 8. Cache | **ALREADY DONE** | `varuna_source_adapters/cache.py::FileCache` — deterministic sha256 key over `product_id`+`bbox`+`time_start`+`time_end`, TTL-based freshness, documented |
| 9. GoldenCaseWorkflow integration | **NOT WIRED — explicit gap** | No live-provider path calls `GoldenCaseWorkflow` today; `RealE2EPipeline` (which `GoldenCaseWorkflow` wraps) consumes AIS/ERA5/CMEMS adapters via `varuna_integration.forcing`/`ais_source`, but Sentinel-1 acquisition is not yet threaded into that same path — see Gaps |
| 10. Modes | **ALREADY DONE (REAL/SIMULATED/UNAVAILABLE)** | `EvidenceMode` — verified end-to-end for the new Sentinel-1 adapter this session (see below). No `NOT_CONFIGURED` value exists as a DISTINCT `EvidenceMode` member — `UNAVAILABLE` is the existing repository term for "this source could not be reached/has no local data" and is what `fetch_with_mode()` already returns; introducing a fifth mode value was judged out of scope (see Gaps) |
| 11. On-demand only | **UNCHANGED** | No Kafka/Flink/Kubernetes/Celery/Airflow existed before this session and none was added |
| 12. Frontend | **NOT TOUCHED** | Explicitly out of scope for a backend/data session; frontend is owned externally per the roadmap image |

## What this session actually built: Sentinel-1

`packages/varuna_source_adapters/sentinel1.py` previously contained:

```python
class Sentinel1Adapter:
    def fetch_scene(self, scene_id: str) -> Any:
        return {"id": scene_id, "data": "mock_s1_data"}
```

— a 5-line stub that did not implement `SourceAdapter` at all (no `fetch`/
`health_check`/`source_id`), had no callers anywhere in the codebase
(confirmed by repo-wide grep before rewriting), and always "succeeded" with
fabricated content regardless of whether real data existed.

**Replaced with a real, tested adapter, mirroring the ERA5/CMEMS pattern
exactly:**

- `health_check()`: true only if the configured root directory contains at
  least one `*.SAFE` product with a `manifest.safe` file.
- `fetch()`: raises `FileNotFoundError` if none exist (never fabricates) —
  `fetch_with_mode()` (pre-existing, unmodified) turns that into
  `EvidenceMode.UNAVAILABLE`, exactly the "NOT_CONFIGURED, not fake data"
  behavior Phase 2 requires, expressed in the repository's own existing
  vocabulary rather than a new one.
- On success: returns the SAFE product's own path plus **real, parsed**
  scene metadata — scene ID, acquisition start/stop (parsed from
  `manifest.safe`'s `safe:startTime`/`safe:stopTime`), product type,
  polarizations (parsed from measurement filenames), and a sha256 of the
  manifest (not the multi-GB measurement GeoTIFFs — documented as such,
  not silently partial).
- **Deliberately does not** run radiometric calibration or NETRA tiling —
  that stays in `varuna_data_eng.preprocessing.sentinel1_grd_calibration`
  and `varuna_integration.netra_boundary`, unmodified, per "do not silently
  alter NETRA input semantics."

**Verified against a real local SAFE product**, not just synthetic paths:
`data/raw/sentinel1_grd/mc20_2023-01-15/S1A_IW_GRDH_1SDV_20230115T000206_...SAFE`
(the same product `provenance.json` records as MC20's real SAR source).
Live run confirmed:

```
health_check (real dir): True
mode: real
artifact_path: data\raw\sentinel1_grd\mc20_2023-01-15\S1A_IW_GRDH_...SAFE
scene_id=S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2
product_type=GRD; polarizations=VH,VV
acquisition=2023-01-15 00:02:06.898608+00:00..2023-01-15 00:02:31.897346+00:00
manifest_sha256=6ef39f7b5d4724c45314fe1de69cbba7995eb0e33583575a8036446e1dbab321

missing-dir mode: unavailable, result: None
```

## Tests

`tests/unit/test_sentinel1_adapter.py` — 6 tests, all passing (none
skipped — the real-SAFE-product tests ran against genuine local data, not
a synthetic fixture):

- missing directory → `UNAVAILABLE`, not fabricated
- empty directory → `health_check() is False`
- `fetch()` on an unavailable source raises `FileNotFoundError`
- real SAFE product → `EvidenceMode.REAL`, correct artifact path/provenance
- scene metadata is genuinely parsed (acquisition ordering, polarization
  set, 64-char sha256), not invented
- `source_id`/`ADAPTER_VERSION` stability

Targeted regression run this session (adapter/forcing-related tests):
**53 passed, 0 failed.** No pre-existing test imported the old
`fetch_scene()` method (verified by repo-wide grep before and after the
change) — the rewrite has zero blast radius on other code.

## Providers: working / unavailable / auth requirements

| Provider | Status | Auth needed for what exists today |
|---|---|---|
| Sentinel-1 | **REAL** (local `.SAFE`, this session) | None — reads local disk. Live Copernicus/ASF API acquisition not implemented (would need real credentials this environment does not have configured) |
| AIS | **REAL** (pre-existing) | None for the local bronze/track files it reads |
| ERA5 | **REAL** (pre-existing, local GRIB only) | None for local files; live CDS API fetch not implemented (would need a CDS API key) |
| CMEMS | **REAL** (pre-existing, local NetCDF only) | None for local files; live Copernicus Marine API fetch not implemented (would need Copernicus Marine credentials) |

No provider in this repository currently performs a live remote API call.
All four are honestly "real data, read from a local, already-acquired
copy" — not simulated, but also not on-demand-from-the-internet. This was
true before this session for AIS/ERA5/CMEMS and is now also true for
Sentinel-1.

## Cache

Unmodified this session. `FileCache` (deterministic sha256 key over
`product_id`+`bbox`+`time_start`+`time_end`, TTL-checked freshness) already
existed and was not exercised by the new Sentinel-1 adapter (SAFE products
are read directly from their acquisition location, not cached/copied — the
existing `FileCache.put()` copies a file into the cache directory, which
would duplicate a multi-GB product; not invoked here for that reason,
documented rather than silently worked around).

## Honest gaps (not silently worked around)

1. **`GoldenCaseWorkflow` never calls `Sentinel1Adapter`.** The canonical
   case-execution path's SAR ingestion is `varuna_integration.netra_boundary`
   reading pre-built Event Gold tiles (`data/gold/events/mc20_v0_1/sar/`),
   not a live per-run SAFE acquisition. Wiring a fresh `Sentinel1Adapter.fetch()`
   result into that path — deciding whether it replaces or supplements
   Gold-tile reading, and how a freshly-fetched SAFE product becomes NETRA
   input tiles on demand — is a real design decision this session did not
   make. Named here for a future step, not defaulted silently.
2. **No unified "NormalizedArtifact" contract across all four providers.**
   Each has its own shape (`ForcingCube` for ERA5/CMEMS, `VesselTrack` for
   AIS, a raw `FetchResult` for Sentinel-1). Introducing one shared contract
   is a `varuna_contracts` schema change (its own ADR, per that package's
   locked-contract convention) — not attempted here.
3. **Data Guard does not yet validate the four provider artifacts
   specifically** (SAR polarization support, AIS coordinate/timestamp
   sanity, ERA5/CMEMS coverage/units) — it validates case-level slick
   points/tracks today. Extending it per-provider is real, scoped work not
   attempted this session.
4. **No live remote API fetch exists for any of the four providers** — all
   are "real local file, honestly labeled REAL" rather than "fetched live
   just now." This was true before this session (AIS/ERA5/CMEMS) and
   remains true for the newly-added Sentinel-1 adapter. No credentials for
   any live provider API were available in this environment, and none were
   fabricated or worked around.
5. **Phases 5, 6, 9, 10 (NOT_CONFIGURED as a distinct mode), 12** were
   reviewed but not implemented/extended this session — see the table
   above for the exact current state of each.

## Definition of done — actual status against the task's own checklist

1. Provider interfaces exist — **yes (pre-existing)**
2. At least one supported real provider works — **yes, four (AIS/ERA5/CMEMS
   pre-existing + Sentinel-1 this session), all in local-file-real mode**
3. Data Guard validates inputs — **partially (case-level, not per-provider)**
4. Normalized artifacts have provenance — **yes, per-provider shape, not unified**
5. Cache works — **yes (pre-existing), not exercised by Sentinel-1 (documented why)**
6. GoldenCaseWorkflow remains canonical — **yes — nothing in this session created
   a second case pipeline; no `LiveCaseWorkflow` was introduced**
7. LIVE/REPLAY/SIMULATED distinction explicit — **yes, expressed via the
   existing `EvidenceMode`/`EngineMode` vocabulary; no separate
   `NOT_CONFIGURED` enum member was added (see gap 5)**
8. Cockpit exposes data provenance — **not touched (frontend explicitly out of scope)**
9. Replay tests remain green — **yes, verified: targeted regression 53/53 passed**
10. Chromium E2E passes — **not run this session (no frontend change to test)**
11. Limitations documented honestly — **this report**

## Recommendation

Treat this as a partial pass, honestly reported as such: the live-data
*foundation* (interfaces, provenance, cache, three of four real adapters)
was already solid going into this session; this session closed the one
adapter that was still a fabricated stub (Sentinel-1) and verified it
against real local data end to end. The larger integration work —
threading a freshly-fetched Sentinel-1 scene into `GoldenCaseWorkflow`'s
existing Gold-tile-based SAR path, a unified normalized-artifact contract,
and per-provider Data Guard rules — is real, scoped future work, not
completed here.
