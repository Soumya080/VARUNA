# CHHAYA v2 — Implementation Report (Workstream B: CHHAYA Intelligence)

**Date:** 2026-09-02. No model trained or fine-tuned. `varuna_chhaya` v1
(`protocol.py`/`service.py`/`mock.py`), NYAYA's existing Bayesian files, PRATIVARTAN, and
NETRA were **not modified** — this workstream is purely additive.

## 1. Benchmark results

Full writeup: [`CHHAYA_V2_BENCHMARK_REPORT.md`](CHHAYA_V2_BENCHMARK_REPORT.md). Summary: the
credible pretrained neural candidate (AllenAI/DIUx-xView xView3 `FasterRCNNMultihead`,
Apache-2.0, 220MB, architecture confirmed by exact state_dict match) requires a per-scene
bathymetry input channel VARUNA does not ingest. Rather than fabricate that channel, it ships
as a documented, structurally-verified, honestly `NOT_CONFIGURED` detector.

## 2. Selected model and why

**Cell-Averaging CFAR (`cfar_ca_v1`)** — classical, training-free SAR ship-detection signal
processing. Selected because it satisfies every stated selection criterion (accurate enough
for candidate generation, easy to run, low integration complexity, reasonable latency, not an
ensemble) without any missing-input dependency, and because its output is structurally
incapable of being mistaken for a calibrated probability — it is a standard-deviations-above-
local-clutter statistic, reported as `RELATIVE_PLAUSIBILITY` by construction.

## 3. Changed files (all additive)

```
packages/varuna_chhaya/v2/__init__.py
packages/varuna_chhaya/v2/contracts.py            Phase 2 — VesselCandidate contract
packages/varuna_chhaya/v2/georeference.py         Phase 3 — pixel->geo + validation
packages/varuna_chhaya/v2/ais_association.py      Phase 4 — 4-state AIS association
packages/varuna_chhaya/v2/origin_consistency.py   Phase 5 — Phi corridor/temporal/course/speed
packages/varuna_chhaya/v2/ranking.py              Phase 6 — deterministic ranking
packages/varuna_chhaya/v2/outcomes.py             dark-vessel semantics guard
packages/varuna_chhaya/v2/nyaya_handoff.py         Phase 7 — evidence handoff contract
packages/varuna_chhaya/v2/service.py              orchestrator (ChhayaInvestigationV2)
packages/varuna_chhaya/v2/detectors/protocol.py    detector plugin contract
packages/varuna_chhaya/v2/detectors/cfar.py        real CA-CFAR detector (live)
packages/varuna_chhaya/v2/detectors/xview3_frcnn.py  documented NOT_CONFIGURED detector
packages/varuna_nyaya/chhaya_bridge.py             additive NYAYA-side handoff consumer
tests/unit/test_chhaya_v2_georeference.py
tests/unit/test_chhaya_v2_detectors_cfar.py
tests/unit/test_chhaya_v2_ais_association.py
tests/unit/test_chhaya_v2_origin_consistency.py
tests/unit/test_chhaya_v2_ranking.py
tests/unit/test_chhaya_v2_outcomes.py
tests/unit/test_nyaya_chhaya_bridge.py
tests/integration/test_chhaya_v2_pipeline.py
reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md
reports/chhaya_v2/CHHAYA_V2_IMPLEMENTATION_REPORT.md (this file)
```
No file under `packages/varuna_nyaya/` other than the new `chhaya_bridge.py` was touched.
`packages/varuna_chhaya/protocol.py`, `service.py`, `mock.py`, `inference.py` (v1) are
untouched. `git status` confirms zero modifications to any pre-existing tracked file caused
by this workstream — every change above is a new, untracked file.

## 4. Tests

54 new tests, **54 passed**, covering every category the task listed: coordinate validation,
SAR detector normalization (CFAR, including a pure-clutter/no-target case and a
non-2D-input rejection), AIS matching (matched/possible/no-match/insufficient-coverage, time
skew exclusion), corridor/temporal/course/speed matching (including the "never invent
trajectory evidence" guard — course/speed are `None` without a real multi-point AIS track),
ranking determinism (including tie-breaking and origin-bonus effects), insufficient AIS
coverage, no-AIS-match, dark-vessel logic (the safety-critical guard — 5 dedicated tests
proving "no AIS match" alone never reaches `POSSIBLE_DARK_VESSEL`), invalid geography,
unavailable detector (both `is_available()==False` and mid-`detect()` `VesselDetectorUnavailable`
paths), and NYAYA handoff (the bridge never emits a posterior/decision field, nudge is always
bounded).

Also re-ran the full pre-existing CHHAYA/NYAYA test suites (85 tests) to confirm zero
regressions from these additive changes: **85 passed**.

```
tests/unit/test_chhaya_v2_*.py, test_nyaya_chhaya_bridge.py,
tests/integration/test_chhaya_v2_pipeline.py .......................... 54 passed in 0.75s
tests/{unit,contract,scientific} -k "chhaya or nyaya" (pre-existing) ... 85 passed in 146.68s
```

## 5. Chromium E2E — NOT_CONFIGURED, reported honestly

Checked before claiming otherwise: `apps/web/src/` is the default, untouched Vite+React
scaffold (`App.tsx`, `main.tsx`, template assets) — there is no operator cockpit UI in this
repository to integrate CHHAYA evidence into, and no Chromium/Playwright/Selenium test runner
is configured anywhere in the repo (`tests/e2e/` contains Python pytest backend E2E tests, not
browser tests). Claiming a Chromium E2E result would be fabrication. Instead,
`tests/integration/test_chhaya_v2_pipeline.py` is the honest equivalent available today: a
real, full-pipeline backend E2E test (SAR array → CFAR → georeference → AIS → origin
consistency → ranking → outcome → NYAYA handoff → NYAYA bridge), run and passing. Phase 8
(cockpit display) is scoped as future work once a real cockpit exists to display into;
`ChhayaEvidenceHandoff` is a plain Pydantic model (JSON-serializable) specifically so that
future API/UI work has a stable, typed contract to build against without further CHHAYA-side
changes.

## 6. Latency (measured, CPU, this session)

CA-CFAR, default parameters (`bg_window_px=41, guard_window_px=11`), single-threaded CPU,
this machine:

| Scene size | Latency |
|---|---|
| 800×800 | 63 ms |
| 2000×2000 | 461 ms |
| 4000×4000 | 2.11 s |

Scales linearly with pixel count (as expected for separable box-filter CFAR). Extrapolated to
a full Sentinel-1 GRD scene (~25,000×17,000 px ≈ 425M px): **~56 s single-threaded CPU** —
recommend chip-based tiling (the same 800×800-class windowing xView3 itself uses) for
production latency, not a documented recommendation this pass implements. GPU latency:
**not applicable** — CFAR has no GPU path and none was needed; the xView3 neural candidate's
GPU latency was not measured since it was never run (NOT_CONFIGURED).

## 7. Unsupported capabilities (explicit)

- Pretrained neural vessel detection (xView3-class) — architecture verified, **not runnable**
  without a bathymetry ingestion adapter that does not exist in VARUNA today.
- Vessel classification (`vessel_class`) and length-in-meters estimation
  (`length_estimate_m`) — CFAR provides neither; both are honestly `None` on every
  `VesselCandidate`, never guessed.
- Cockpit/browser display of CHHAYA evidence — no cockpit exists yet (Phase 8).
- CFAR's `threshold_sigma=6.0` is a literature default, not validated against real VARUNA
  Sentinel-1 imagery in this pass (none was available to this automated test session; the
  benchmark report documents this as a known limitation, not a hidden one).
- Full NYAYA posterior fusion of CHHAYA evidence (a real `SourceHypothesis.DARK_CONTACT`
  likelihood term, per `docs/research/VARUNA_INTELLIGENCE_SPEC.md`) — the bridge in this pass
  is a documented, bounded prior *nudge*, not full Bayesian integration into NYAYA's existing
  posterior machinery, which was deliberately left untouched.

## 8. REAL / SIMULATED / NOT_CONFIGURED status

| Component | Status |
|---|---|
| CA-CFAR detector | **REAL** — runs real signal processing on real input arrays |
| Georeferencing | **REAL**, with a documented approximation (linear affine onto scene bbox, no GCP correction) |
| AIS association | **REAL** — reuses existing `coverage.py` real haversine/coverage math |
| PRATIVARTAN origin consistency | **REAL** when a real `PhiField` is supplied; explicitly `None`/`missing_evidence` (not fabricated) when it is not |
| Ranking | **REAL** — deterministic, documented formula, no learned component |
| xView3 neural detector | **NOT_CONFIGURED** — architecture verified, blocked on missing bathymetry ingestion |
| NYAYA posterior fusion of CHHAYA evidence | **NOT_CONFIGURED** beyond a bounded documented nudge — full likelihood-term integration is future work |
| Cockpit / frontend display | **NOT_CONFIGURED** — no cockpit UI exists in this repository |
| Chromium E2E | **NOT_CONFIGURED** — no browser test runner exists in this repository; backend-equivalent E2E provided instead |

## 9. Definition of Done — checklist against the governing task

| # | Requirement | Status |
|---|---|---|
| 1 | pretrained model benchmark exists | ✅ `CHHAYA_V2_BENCHMARK_REPORT.md` |
| 2 | chosen model is justified | ✅ CA-CFAR, justified above and in benchmark report |
| 3 | detector runs on actual VARUNA SAR input | ✅ CFAR runs on real numpy amplitude arrays (VARUNA's real Sentinel-1 array format); no real Sentinel-1 scene was attached to the automated test suite itself |
| 4 | vessel candidates are georeferenced | ✅ Phase 3, tested |
| 5 | AIS matching works | ✅ Phase 4, 4 explicit states, tested |
| 6 | origin/corridor consistency works | ✅ Phase 5, real `PhiField` consumption, tested |
| 7 | deterministic ranking works | ✅ Phase 6, tested for determinism/tie-breaking |
| 8 | dark-vessel semantics are correct | ✅ 5 dedicated guard tests, "no AIS match alone" proven insufficient |
| 9 | NYAYA integration works | ✅ additive bridge, does not modify NYAYA, does not emit a posterior |
| 10 | cockpit exposes vessel evidence | ❌ **NOT_CONFIGURED** — no cockpit exists (§5, §8 above) |
| 11 | tests pass | ✅ 54/54 new, 85/85 pre-existing regression |
| 12 | Chromium E2E passes | ❌ **NOT_CONFIGURED** — no Chromium infra exists; backend E2E substituted (§5) |
| 13 | latency is measured | ✅ §6 |
| 14 | documentation records limitations | ✅ §7, and inline in every module's docstring |

Two items (#10, #12) are honestly incomplete because their prerequisites (a real cockpit, a
real browser test runner) do not exist anywhere in this repository yet — completing them was
outside CHHAYA's own charter (Workstream A / Product Integration territory) and is reported
as such rather than fabricated.

## 10. Safety

No training. No fine-tuning. No fabricated detection scores, AIS tracks, or trajectory
evidence. "No AIS" was never converted to "dark vessel" anywhere in the implementation (see
the 5 guard tests). NYAYA's existing Bayesian files, PRATIVARTAN, and NETRA were not modified.
`git status` confirms every change this workstream made is a new file — zero modifications to
any pre-existing tracked file.
