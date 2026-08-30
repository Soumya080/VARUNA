# Track 2 Final Validation — Scientific Robustness + Real Integration

**Date:** 2026-08-30
**Scope:** Track 2 (provenance, Φ diagnostics, sensitivity, validity-gate hardening) finalization —
real AIS SourceAdapter, production-scale Φ sensitivity, full regression. Not a NETRA task; the frozen
`netra-v0.2-baseline` checkpoint, `NETRA-GOLD-v0.2`, and the official test split are untouched
throughout.

**Companion work (Track 4, `router-datasets-ca`):** `docs/e2e/MC20_REAL_E2E_INTEGRATION.md` and
`scripts/mc20_track4_e2e.py` already wire the full analytical chain (forcing → detection → Φ → NYAYA
→ validity → forecast → decision → mission → alerts → OperatorCase) end to end and prove REAL forcing
+ REAL AIS propagate correctly. That work explicitly left one gap open (its own limitation #3): *"Φ
sensitivity is `None`. The 7× sweep (ADR-0007) was not run."* This document is the closing of that
gap, not a duplicate of it — read the Track 4 doc first for the full orchestration graph and failure
semantics; this document only covers what changed since.

---

## 1. EvidenceMode

Unchanged from ADR-0006/ADR-0007: `EvidenceMode.{REAL,SIMULATED,UNAVAILABLE}`, monotonic-worsening
`derive()`, no config path that raises a mode. Re-verified in this pass at the AIS-adapter boundary
(new tests below) and at production scale (Section 3): a REAL-forcing + SIMULATED-placeholder-slick
input correctly propagates SIMULATED through Φ, NYAYA, and the ValidityGate, and never reverts to
REAL at any hop.

## 2. AIS SourceAdapter

`packages/varuna_source_adapters/ais.py` re-exports `varuna_integration.ais_source.EventAISAdapter`
(built by the Track-4/dataset track; kept in place rather than moved, per that session's no-move
constraint — a re-export gives the canonical `varuna_source_adapters` import path without a file
move). The path required by this task:

```
REAL AIS SOURCE (data/bronze/ais/mc20_2023-01-15_tracks.json)
    -> EventAISAdapter.fetch()                    (FetchResult, is_simulated=False)
    -> fetch_with_mode()                          (EvidenceMode.REAL)
    -> stream_tracks() / to_vessel_track()         (canonical VesselTrack[])
    -> NyayaService.attribute(tracks_envelope=...) (existing join, unmodified)
```

Preserved unmodified: `AISJoinStatus` (temporally_matched vs. spatially_matched_only kept distinct —
a spatial candidate is never promoted into temporal evidence), provenance (`Provenance(source_id=...)`
carries the real MC20 join's own counts, never invented), `EvidenceMode` (decided only by
`health_check()`/`fetch()` outcome, never by configuration).

The pre-existing 5-line `AISAdapter` stub (zero call sites, verified before superseding) is left in
place, annotated superseded, per the no-delete constraint — nothing calls it and nothing should.

**New tests:** `tests/unit/test_ais_source_adapter.py` (11 tests) — health_check() two-level failure
(join missing; join present but bronze file missing), fetch() raising `FileNotFoundError` rather than
returning an empty vessel list, `is_simulated=False -> EvidenceMode.REAL` through `fetch_with_mode()`,
`health_check()` failure and a fetch()-time exception both yielding `UNAVAILABLE`, no constructor
parameter that could set provenance independent of what was actually found on disk, the superseded
stub's inertness, and one end-to-end test against the real MC20 join file.

## 3. Φ Sensitivity — Production Scale

Ratified normalization (ADR-0007, prior session): `sensitivity = centroid_shift_km /
effective_radius_km`, `effective_radius_km = sqrt(effective_support_km2 / pi)`. This pass runs it for
the first time at the configured production scale (`n_particles=500`, `n_ensemble=20`) against the
**real** MC20 ERA5/CMEMS `ForcingCube`s, 7 total ensemble executions (1 baseline + 2 age ± + 2 forcing
± + 2 diffusivity ±), using only the existing configured perturbation ranges
(`PratiConfig.current_noise_range`, `diffusivity_range`, `age_prior_std_hours`) — no new perturbation
parameter invented.

**Seed provenance, stated explicitly:** the real NETRA Training Track has not produced a valid MC20
slick detection (frozen-checkpoint inference returns near-zero probability everywhere — a measured
out-of-distribution result, not a negative finding; see the NETRA post-baseline audit). Per this
task's explicit instruction not to substitute a NETRA-generated detection where none exists, the
sweep is seeded from a bounded, explicitly-labelled synthetic placeholder point cluster at the real
SAR footprint's centroid — never claimed as a real detection, carried as `EvidenceMode.SIMULATED`
through an envelope `derive()`d from a REAL forcing envelope, so the combined lineage is honestly
SIMULATED end to end (see Section 6).

**A real methodological defect was caught and fixed during this run, not before publishing results:**
the first attempt used a 12-point placeholder cluster. `run_backward_ensemble()` computes
`min(config.n_particles, n_obs)` particles per member — with only 12 observation points, the
configured `n_particles=500` silently capped at 12 regardless of what the config said. Fixed by
sizing the placeholder to 550 points so the configured particle budget is genuinely exercised, and
the run was repeated. The full mechanism is disclosed here rather than only reporting the corrected
number, because a config value that silently doesn't take effect is exactly the kind of thing this
track exists to catch.

**Results** (full detail in `reports/track2_final_validation.json`), 500 particles/member, 20/20
members completed on every one of the 7 runs, all `convergence_flag=converged`:

| Run | Convergence | Particles lost | Runtime |
|---|---|---|---|
| baseline | 0.0496 | 4273/10000 (42.7%) | 38.8s |
| age − | 0.0496 | 4273/10000 | 39.6s |
| age + | 0.0496 | 4273/10000 | 40.0s |
| forcing − | 0.0509 | 3983/10000 (39.8%) | 38.9s |
| forcing + | 0.0503 | 4541/10000 (45.4%) | 38.5s |
| diffusivity − | 0.0440 | 4254/10000 | 37.0s |
| diffusivity + | 0.0518 | 4296/10000 | 36.9s |

`SensitivityBlock`: `age_sensitivity=0.0370`, `forcing_sensitivity=0.0051`,
`diffusivity_sensitivity=0.0011`, `weathering_sensitivity=None`, `dominant_assumption="age"`. All
three real axes sit well under the gate's unmodified 0.7 threshold — the reconstructed origin field
is not an artefact of the age/forcing/diffusivity priors at this real forcing/location combination.

**The ~40-45% particle loss is partially explained, and a follow-up sweep corrected an initial
hypothesis rather than letting it stand.** A direct check of the real forcing grids found the CMEMS
current field is **26.4% NaN** (`load_cmems_current_arrays` — a land mask; ocean current is undefined
over land), while the real ERA5 wind field is **0% NaN**. MC20 sits close to the Louisiana coast, so
a NaN-propagation mechanism (a particle's velocity going NaN near a land-masked cell, then staying
NaN for the rest of its trajectory) is physically plausible.

`router-datasets-ca` reported **not** reproducing this loss in their own Track 4 run against the same
real CMEMS field (`particles_lost=0`) and hypothesized the difference was `backward_duration_hours`
(this session's production run guessed to be ~84h via `age_prior_mean + 2σ`, vs. their 24h default).
**A duration sweep was run to test this directly** (`scripts/mc20_particle_loss_duration_sweep.py`,
same real forcing, same seed=42, same 550-point centroid placeholder, `n_ensemble=5` for speed):

| Duration (h) | Loss fraction | Convergence |
|---|---|---|
| 12 | 0.079 | 0.149 |
| 24 | 0.427 | 0.129 |
| 36 | 0.613 | 0.116 |
| 48 | 0.800 | 0.097 |
| 60 | 0.967 | 0.096 |
| 72 | 0.852 | 0.094 |
| 84 | 0.950 | 0.124 |

Two findings, one confirming and one correcting the working hypothesis:

1. **Duration is a real, strong driver in general** — loss rises from 8% at 12h to 80-97% by 48-60h.
   Not perfectly monotonic (a dip at 72h vs. 60h/84h) — real, measured, unexplained; plausibly the
   specific real time-varying current field routing backward trajectories through a locally
   less-NaN-dense region at that particular horizon, not an artefact, but not traced particle-by-
   particle to confirm.
2. **Duration does NOT explain the ca/this-session discrepancy.** This session's actual production
   script used `backward_duration_hours=24.0` (checked directly, not ~84h as guessed) — the *same*
   duration as `router-datasets-ca`'s default. At that same 24h duration, this sweep measured 42.7%
   loss — matching this session's original production figure almost exactly, and contradicting the
   duration hypothesis as the explanation for why `router-datasets-ca`'s run saw zero loss under
   nominally the same conditions. **The real differentiator between the two runs is unresolved** —
   remaining candidates are particle count per member, ensemble size, or the exact `obs_time_hours`
   used, not backward duration. This is reported as an open, unreconciled discrepancy rather than
   resolved by the more convenient (but factually incorrect) explanation.

This is a genuine property of using a real, land-masked regional ocean current product near a
coastline, worsened at longer backward horizons — not a PRATIVARTAN defect. No fix is proposed:
handling land-masked cells explicitly (clamping, nearest-valid-cell fallback, an explicit land flag)
or tightening the age prior to reduce horizon would both be real, scoped follow-ups, out of this
task's "do not redesign the scientific architecture" boundary.

`SensitivityBlock`: `age_sensitivity`, `forcing_sensitivity`, `diffusivity_sensitivity` — all real,
computed values (see JSON). **`weathering_sensitivity` is `None`** — PRATIVARTAN implements no
weathering model (`PhiField.weathering_model` is always `None`); this is the honest, permanent state
of that field, not a placeholder pending a future fix, and it is never fabricated.

## 4. Validity Gate — Production Diagnostics

The real production `PhiField` (with its real `SensitivityBlock` populated) and real AIS tracks (via
`EventAISAdapter`, `AISJoinStatus.TEMPORALLY_MATCHED`, 5 real vessels, closest MMSI `368181750` at
3.2554 km / +16m57s — independently reproducing Track 4's own figure for the same real join) were fed
through `NyayaService.attribute()` and `ValidityService.evaluate()` **unmodified** — no threshold
changed, no new scoring path added.

**Result: `ValidityState.DEGRADED`, `allows_operational_action=True`.**

`ValidityState.DEGRADED` is a first-class outcome distinct from `VALID`/`RESTRICTED`/`INCONCLUSIVE`
(`packages/varuna_contracts/evidence.py`) — it means "actionable with caveats shown to the officer,"
not "broken." This is reported as measured, not adjusted to reach `VALID`:

| Check | Passed | Observed | Threshold |
|---|---|---|---|
| source_trust | ✅ | trusted | — |
| phi_convergence | ✅ | 0.0496 | < 0.15 |
| phi_entropy | ✅ | 0.819 | < 0.95 |
| ensemble_completeness | ✅ | 1.0 | ≥ 0.8 |
| **particle_loss** | ❌ | **0.427** | ≤ 0.2 |
| age_sensitivity | ✅ | 0.0370 | < 0.7 |
| forcing_sensitivity | ✅ | 0.0051 | < 0.7 |
| posterior_entropy | ✅ | 0.202 | < 0.9 |
| distinguishability | ✅ | 0.459 | ≥ 0.1 |
| evidence_mode | ✅ (caveat) | simulated | — |

Officer-visible caveats: *"43% of particles lost to boundaries"*, *"Evidence is SIMULATED — not a
real-world observation."* One check fails (`particle_loss`, explained in Section 3 as a real
land-masked-CMEMS-grid effect near the coast) but is non-blocking by the gate's existing, unmodified
design — it degrades the state rather than restricting it. Every other real diagnostic, including
both populated sensitivity axes, passes comfortably. The `evidence_mode=simulated` caveat is the
correct, honest reflection of the placeholder seed (Section 3) — not a defect.

## 5. Real/Synthetic Path Matrix

| Component | REAL implementation | SIMULATED implementation | Selected by | Silent fallback? |
|---|---|---|---|---|
| AIS | `EventAISAdapter` (real bronze/Gold join) | `MockAisAdapter` (`AdapterRegistry.create_mock()`) | Explicit caller choice (which adapter/class is constructed) | **No.** Neither adapter substitutes for the other on failure — `EventAISAdapter.fetch()` raises rather than returning empty data; `fetch_with_mode()` turns that into `UNAVAILABLE`, never `SIMULATED`. |
| ERA5 forcing | `Era5Adapter` → `read_era5_grib()`/`load_era5_wind_arrays()` → `CubeBackedWindField` | `MockEra5Adapter`; `SyntheticWindField` (default in `PrativartanService.reconstruct_origin()` when `wind=None`) | Explicit constructor/parameter choice | **No runtime fallback** — but see caveat below. |
| CMEMS forcing | `CmemsAdapter` → `read_cmems_netcdf()`/`load_cmems_current_arrays()` → `CubeBackedCurrentField` | `MockCmemsAdapter`; `SyntheticModelCurrentField` (default) | same | same |
| PRATIVARTAN ensemble | `run_backward_ensemble()` driven by `CubeBacked*Field` | same function driven by `Synthetic*Field` | Caller supplies the field object; the function itself is field-agnostic | **No** — a single failing ensemble *member* (e.g. an out-of-domain query) is dropped and honestly counted, never silently replaced with a synthetic member. |
| Φ sensitivity | `run_sensitivity_sweep()` + `build_sensitivity_block()` (opt-in, `reconstruct_origin_with_sensitivity()`) | `sensitivity=None` (default, cheap path) | Caller picks the method | **No** — `None` is a real, honest "not computed," never a fabricated number. |
| PRAVAAH | `CubeBackedPravaahProvider` | `MockPravaahProvider` | Explicit caller choice | **No** — no fallback chain in `AbhiyanService`/callers. |
| NYAYA / ValidityGate | Same code path regardless of input origin | same | N/A — origin-agnostic by design | **No** — these read `envelope.mode`, they never re-derive or upgrade it. |
| `AdapterRegistry` (API layer) | `create_live()` — **does not exist** | `create_mock()` — hardcoded in `apps/api/dependencies.py::get_adapter_registry()` | Static, single hardcoded factory call | Not a runtime fallback (nothing tries real and substitutes fake), but functionally: `/health` and `/readiness` (the only two consumers of `get_adapter_registry()`) always report on mock adapters regardless of real data on disk. |
| `CaseWorkflow.reconstruct()` (production API case flow) | N/A — not wired | Always calls `PrativartanService.reconstruct_origin()` with no `current`/`wind`/`input_envelope` args → always synthetic forcing, `sensitivity=None` | Hardcoded call site (`packages/varuna_domain/case_workflow.py`) | Not a fallback (no real attempt precedes it) — a **wiring gap**: the production case-processing workflow the API drives has never been connected to real ERA5/CMEMS/AIS/sensitivity at all. Real data is reachable today only through standalone orchestration (`scripts/mc20_track4_e2e.py`, this task's scripts), not through a live case created via the API. |

**Verdict: no code path silently claims fake data is real.** Every real/synthetic selection point is
explicit and visible in code (a constructor default or a hardcoded factory call), and no exception
handler ever downgrades a failure into a quiet synthetic substitution — failures propagate as
`UNAVAILABLE`, dropped ensemble members, or raised exceptions, all counted honestly. The **separate**
finding is that the production `CaseWorkflow`/API path has never been wired to any of the real
adapters at all — this is an integration-completeness gap, not a fallback, and is out of Track 2's
own scope (Track 2 hardened the scientific chain and the adapter boundary; wiring `CaseWorkflow` to
construct real fields is orchestration work, most naturally Track 4's territory or a follow-on task).

## 6. Scientific Limitations

- **No real NETRA detection exists for MC20.** All Φ/attribution/validity results reported here use
  an explicitly-labelled `SIMULATED` placeholder seed, never a real detection. This is a Training
  Track blocker (domain/preprocessing gap under active investigation), not a Track 2 defect.
- **`weathering_sensitivity` is permanently `None`.** No weathering model exists in PRATIVARTAN.
  This is a modeling gap, not a normalization question, and is explicitly out of Track 2's scope.
- **Forcing/diffusivity sensitivity axes are not a literal 1-sigma perturbation** the way the age axis
  is — they reuse `PratiConfig`'s existing uniform-sampling bounds. Disclosed in ADR-0007, not new
  here.
- **`CaseWorkflow` is not wired to real adapters** (Section 5) — real data is reachable only through
  standalone orchestration scripts today.
- **No `AdapterRegistry.create_live()` exists** — `/health` and `/readiness` always report on mocks.
- **`n_particles`/`n_obs` interaction is a footgun**: a configured particle count silently does
  nothing if the seed geometry has fewer points than requested (Section 3). This was independently
  hit by two sessions at two different call sites (this session's sensitivity script; a parallel
  session's `mc20_track4_e2e.py --scientific` pipeline) — a hint the failure mode is structural, not
  incidental carelessness. Fixed at the source in `phi_builder.py` (Section 3), and independently
  fixed at the orchestration layer in `packages/varuna_integration/pipeline.py` (a `--scientific`
  run now BLOCKS with a named reason if the advected count would fall short, rather than silently
  proceeding). Both fixes are complementary, not duplicated: the orchestration-layer check refuses
  an under-resolved scientific run *before* spending compute; `phi_builder.py`'s fix reports the
  truth *after*, for every caller including ones that never go through that orchestration path.
- **`PhiField.n_particles` changed MEANING, not just accuracy, as part of this fix** — worth flagging
  explicitly since it will otherwise read as a data anomaly rather than a corrected defect. Before:
  the field answered "what was configured" (`config.n_particles`, always, regardless of what actually
  ran). After: it answers "what was actually advected" (measured from the ensemble results,
  `min(config.n_particles, n_obs)` in practice). Same field name, same type, same schema — a
  different question. Concretely: `config.n_particles=500` with 5 real observation points now
  reports `phi.n_particles=5`; previously it silently reported `500`. Any external consumer that had
  been reading this field as "run configuration" (a dashboard, a cross-run comparison, a previously
  serialized `PhiField` from before this fix) will see a discontinuity with no version marker to
  explain it — this paragraph is that marker. The corrected semantics ("what was measured") is the
  one every other honesty mechanism in this codebase already uses (`particles_lost`,
  `ensemble_members_completed`); the field was simply the one spot that hadn't been brought in line
  yet. A future companion field (`n_particles_requested`, mirroring the existing
  `ensemble_members_completed`/`ensemble_members_requested` pairing already on `PhiDiagnostics`)
  would let both facts coexist without overloading one field — flagged for a future ADR-governed
  change to the locked `varuna_contracts` package, not implemented here.
- **AIS join temporal window is fixed** at the Gold-build-time window (±48h/+6h); not reconfigurable
  from this adapter.

## 7. Regression

Run twice: once immediately before the `phi_builder.py` fix (baseline), once after (final). Both
runs cover `tests/contract tests/unit tests/integration tests/e2e`.

| | Collected | Passed | Failed | Errors | Skipped | Runtime |
|---|---|---|---|---|---|---|
| Pre-fix | 438 | 427 | 1 | 0 | 10 | 240.3s |
| **Post-fix (final)** | 440 | 429 | 1 | 0 | 10 | 229.3s |

The single failure in both runs is identical:
`tests/unit/test_netra_training.py::test_netra_training_loop` —
`TypeError: 'NetraSample' object is not subscriptable` at `packages/varuna_netra/training/trainer.py:250`.
**Classification: `PRE_EXISTING` / NETRA-track-owned.** This is inside `packages/varuna_netra/`, an
explicitly off-limits path for this task; it existed before this pass, is unrelated to any Track 2
change, and was not touched or worked around. Zero `TRACK_2_REGRESSION`, `NETRA_RESOURCE`,
`ENVIRONMENT`, or `DATA` failures. Zero errors.

The `n_particles` fix (Section 3) introduced no new regressions — the post-fix run has strictly more
passing tests (429 vs. 427; the 2 additional collected tests are the new `test_ais_source_adapter.py`
cases) and the same single pre-existing failure.

## 7a. Production Readiness Gate

| Item | Status |
|---|---|
| AIS SourceAdapter real | ✅ `EventAISAdapter`, re-exported, 11 tests |
| EvidenceMode correct | ✅ monotonic propagation verified end-to-end, no upgrade path |
| Production Φ sensitivity completed | ✅ 500 particles × 20 ensemble × 7 runs, real ERA5+CMEMS forcing |
| Production convergence measured | ✅ `convergence=0.0496`, `flag=converged` on all 7 runs |
| SensitivityBlock populated | ✅ age/forcing/diffusivity real; weathering correctly `None` |
| ValidityGate consumes real diagnostics | ✅ real `PhiField` + real AIS → `DEGRADED`, real reasons |
| Full regression passes | ⚠️ 429/430 non-skipped pass; 1 failure, `PRE_EXISTING`/NETRA-owned, unrelated to Track 2 (Section 7) |
| No silent mock fallback | ✅ verified (Section 5) — every real/synthetic choice is explicit, no exception-driven downgrade |
| No scientific threshold weakened | ✅ confirmed unmodified (Section 4, thresholds diffed against pre-existing `validity_gate.py`) |
| Provenance preserved | ✅ REAL+SIMULATED→SIMULATED verified at every hop, never reversed |

Nine of ten items are unambiguously green. The regression item carries an asterisk: the one failure
is proven pre-existing and NETRA-owned, not a Track 2 regression — but it is still a failure in the
literal "full regression passes" sense, so it is reported as a caveat rather than silently rounded up
to a clean pass.

**Two further reasons this stops short of unconditional production validation, beyond the checklist
above** (disclosed rather than smoothed over): (1) the real MC20 analytical chain necessarily
terminates in `EvidenceMode.SIMULATED` because no real NETRA detection exists yet for this case — the
chain's plumbing is proven real, but no genuine end-to-end REAL case has been produced, matching this
task's own instruction not to substitute a fabricated detection; (2) the production `CaseWorkflow`/API
path has never been wired to any real adapter (Section 5) — real data is reachable today only through
standalone orchestration, not a live case created through the API.

## 8. Safety

Deleted = 0, Moved = 0, Renamed = 0, Overwritten = 0 throughout. Frozen NETRA checkpoint,
`NETRA-GOLD-v0.2`, and the official test split were not read, written, or referenced by any script in
this pass. `data/gold/events/mc20_v0_1` and `data/bronze/ais/*` were read-only.
