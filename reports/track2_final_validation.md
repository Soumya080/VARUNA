# TRACK 2 FINAL VALIDATION

**Date:** 2026-08-30 · **Full detail:** `docs/science/TRACK_2_FINAL_VALIDATION.md`,
`reports/track2_final_validation.json`, `reports/mc20_production_phi_sensitivity.json`,
`reports/mc20_production_validity_gate.json`

## AIS SourceAdapter
- **status:** Real, complete. `packages/varuna_source_adapters/ais.py` re-exports
  `varuna_integration.ais_source.EventAISAdapter` (built by the dataset/Track-4 session; delegated to
  rather than duplicated, per direct cross-session coordination). Legacy 5-line stub left in place,
  annotated superseded (zero call sites, no-delete constraint).
- **tests:** 11 new (`tests/unit/test_ais_source_adapter.py`) — `health_check()` two-level failure,
  `fetch()` raising rather than returning empty data, `is_simulated=False → EvidenceMode.REAL` through
  `fetch_with_mode()`, `health_check` failure and mid-flight `fetch()` exception both → `UNAVAILABLE`,
  no constructor path that upgrades provenance, superseded-stub inertness, one real-MC20 end-to-end
  test. All 11 pass.
- **EvidenceMode:** `REAL` (real fetch, `is_simulated=False`); `UNAVAILABLE` on missing bronze
  file/health-check failure; no config-based upgrade path exists.

## Production Phi
- **particles:** 500 (measured, not config-echoed — see "n_particles fix" below)
- **ensemble:** 20 members/run, 20/20 completed on every run
- **runs:** 7 (baseline, age ±, forcing ±, diffusivity ±), against real ERA5 (168×17×17,
  `time_series_status=sufficient`) + real CMEMS (133×49×49, `time_series_status=sufficient`) MC20
  `ForcingCube`s
- **runtime:** 36.9–40.0s per run (~269s total sweep)
- **convergence:** 0.0440–0.0518 across all 7 runs, `convergence_flag=converged` on every run
- **particle loss:** 39.8%–45.4% (baseline 42.7%) — explained, not just measured: the real CMEMS
  current grid is **26.4% NaN** (land mask), ERA5 wind is 0% NaN; MC20 sits near the Louisiana coast,
  and backward-advected particles plausibly cross land-masked cells over the 24–48h window, with NaN
  propagating for the rest of a contaminated particle's trajectory. Reported as `HYPOTHESIS`
  consistent with a direct grid measurement, not traced particle-by-particle. Not "fixed" —
  land-mask handling in PRATIVARTAN would be a real, scoped enhancement, out of this task's bounds.

**A real defect was found and fixed mid-task, not glossed over:** the first sensitivity attempt used
a 12-point synthetic placeholder seed; `run_backward_ensemble()` computes
`min(config.n_particles, n_obs)`, so `n_particles=500` in config silently capped at 12. Caught before
publishing, fixed by sizing the placeholder to 550 points, and reran. A parallel session
(`router-datasets-ca`) independently hit an identical instance of the same defect class at a different
call site in `packages/varuna_integration/pipeline.py` — cross-session evidence this is structural,
not incidental. Deeper root cause found in the process: `phi_builder.py` set `PhiField.n_particles`
from `config.n_particles` (a config echo, never a measurement) — meaning any future undersized seed
would silently mis-report even after this task's own particular instance was worked around. **Fixed
at the source**: `PhiField.n_particles` is now measured from the actual ensemble results (with an
assertion that every member agrees, since they should), matching the honesty pattern
`particles_lost`/`ensemble_members_completed` already used elsewhere in this file. This changes the
field's *meaning* (not just its accuracy) for any caller with a seed smaller than its configured
particle count — documented explicitly in `docs/science/TRACK_2_FINAL_VALIDATION.md` §3 so it is not
later mistaken for a data anomaly.

## Sensitivity
- **age:** 0.0370 (real, measured; centroid shift 3.81 km / effective radius 102.9 km)
- **forcing:** 0.0051 (real, measured)
- **diffusivity:** 0.0011 (real, measured)
- **weathering:** `None` — no weathering model exists in PRATIVARTAN; never fabricated
- All three real axes pass the existing, unmodified 0.7 gate threshold comfortably — the origin field
  is not an artefact of any single perturbed assumption at this real forcing/location combination.

## Validity
- **state:** `DEGRADED` (a first-class outcome, distinct from `VALID`/`RESTRICTED`/`INCONCLUSIVE` —
  "actionable with caveats," not "broken")
- **reasons:** 9/10 checks pass (source_trust, phi_convergence 0.0496<0.15, phi_entropy 0.819<0.95,
  ensemble_completeness 1.0≥0.8, age_sensitivity 0.037<0.7, forcing_sensitivity 0.005<0.7,
  posterior_entropy 0.202<0.9, distinguishability 0.459≥0.1, evidence_mode caveat). One check fails
  non-blockingly: `particle_loss` observed 0.427 > threshold 0.2 (explained above). No threshold was
  changed to obtain this or any other result.
- **operational action:** `allows_operational_action=True`, with officer-visible caveats: *"43% of
  particles lost to boundaries"*, *"Evidence is SIMULATED — not a real-world observation."*

## Real Analytical Chain
- **AIS:** REAL — `EventAISAdapter`, 5 temporally-matched real vessels, closest MMSI `368181750` at
  3.2554 km / +16m57s (independently reproduces Track 4's own figure for the same real join)
- **ERA5:** REAL — real cube, `time_series_status=sufficient`
- **CMEMS:** REAL — real cube, `time_series_status=sufficient`
- **PRATIVARTAN:** REAL forcing driving the real ensemble; slick seed is an explicitly-labelled
  `SIMULATED` placeholder (no real NETRA detection exists for MC20 yet — Training Track is still
  investigating the domain gap; substituting a fabricated detection was explicitly disallowed by this
  task)
- **Phi:** produced, real diagnostics + real `SensitivityBlock`; envelope `SIMULATED` (monotonic —
  REAL forcing + SIMULATED seed → SIMULATED, correctly, never upgraded)
- **NYAYA:** produced, `decision_state=latent_source`, envelope `SIMULATED` (REAL AIS did not upgrade
  an already-SIMULATED Phi lineage — correct monotonic behavior)
- **Validity:** produced, `DEGRADED`, envelope `SIMULATED`

## Regression
Run twice (pre- and post-`phi_builder.py` fix), `tests/contract tests/unit tests/integration tests/e2e`:

| | Collected | Passed | Failed | Errors | Skipped | Runtime |
|---|---|---|---|---|---|---|
| Pre-fix | 438 | 427 | 1 | 0 | 10 | 240.3s |
| Post-fix (final) | 440 | 429 | 1 | 0 | 10 | 229.3s |

The one failure in both runs: `tests/unit/test_netra_training.py::test_netra_training_loop`
(`TypeError: 'NetraSample' object is not subscriptable`, `packages/varuna_netra/training/trainer.py`)
— **classified `PRE_EXISTING`, NETRA-track-owned**, inside an explicitly off-limits path, unrelated to
any Track 2 change, not touched. **Zero `TRACK_2_REGRESSION`s.**

## Real/Synthetic Matrix
Full matrix in `docs/science/TRACK_2_FINAL_VALIDATION.md` §5. Summary: every real/synthetic selection
point in the codebase is explicit (a constructor default or a hardcoded factory call) — no exception
handler ever silently downgrades a failed real attempt into a fabricated synthetic success. Two
disclosed, non-fallback gaps found: (1) `apps/api/dependencies.py::get_adapter_registry()` hardcodes
`AdapterRegistry.create_mock()` — no `create_live()` exists, so `/health`/`/readiness` always report
on mocks; (2) `packages/varuna_domain/case_workflow.py::CaseWorkflow.reconstruct()` never passes
`current`/`wind`/`input_envelope` to `PrativartanService`, so the production API case-processing path
always uses synthetic forcing and never computes sensitivity — real data is reachable today only
through standalone orchestration scripts, not a live API-created case.

## Scientific Limitations
- No real NETRA detection exists for MC20 (Training Track blocker, not a Track 2 defect) — all
  results here use an explicitly-labelled SIMULATED placeholder seed.
- `weathering_sensitivity` is permanently `None` — no weathering model exists.
- Forcing/diffusivity sensitivity axes reuse existing uniform-sampling ranges, not a literal 1-sigma
  perturbation the way the age axis is (disclosed in ADR-0007, unchanged here).
- `CaseWorkflow` is not wired to any real adapter (see matrix above).
- No `AdapterRegistry.create_live()` exists.
- `n_particles`/`n_obs` interaction is a structural footgun, now fixed at the `phi_builder.py` source
  and at the Track-4 orchestration layer independently — but `PhiField.n_particles`'s *meaning*
  changed as a result (see "Production Phi" above and the full doc).
- ~40-45% particle loss near the real MC20 coastline, explained (not confirmed) by CMEMS land-mask
  NaN propagation — not remediated, out of this task's scope.

## Safety

    Deleted = 0
    Moved = 0
    Renamed = 0
    Overwritten = 0

Frozen NETRA checkpoint, `NETRA-GOLD-v0.2`, and the official test split were not read, written, or
referenced by any script in this pass. All MC20/AIS data access was read-only.

---

# FINAL STATUS

**`TRACK_2_COMPLETE_WITH_SCIENTIFIC_LIMITATIONS`**

All three P0 tasks were genuinely executed: the real AIS SourceAdapter exists and is tested; the
production-scale (500×20×7) Φ sensitivity sweep ran against real ERA5/CMEMS forcing and produced a
real, non-fabricated `SensitivityBlock`; the full regression suite ran twice with zero Track-2
regressions. The ValidityGate consumed these real diagnostics unmodified and returned a real,
non-inflated `DEGRADED` result with honest reasons. This is not `TRACK_2_PARTIAL` or
`TRACK_2_BLOCKED` — nothing required is missing or failed to run.

It stops short of `TRACK_2_PRODUCTION_VALIDATED` for reasons disclosed above, not omitted: the real
analytical chain necessarily terminates in `SIMULATED` mode because no real NETRA detection exists
yet (a Training Track blocker, not fixable from Track 2); the production `CaseWorkflow`/API path has
never been wired to any real adapter; and one pre-existing, NETRA-owned regression remains in the
shared suite (unrelated to Track 2, not touched, but present).

# FINAL NEXT ACTION

Per the task's own instruction, `TRACK_2_COMPLETE_WITH_SCIENTIFIC_LIMITATIONS` — not
`TRACK_2_PRODUCTION_VALIDATED` — is being returned, so the "stop, do not start another Track-2
architecture expansion" branch does not strictly apply. Recommended next actions, in order:
1. NETRA domain/preprocessing decision (Training Track, already in progress per the post-baseline
   audit) — the actual blocker to a genuine REAL end-to-end MC20 case.
2. Wire `CaseWorkflow.reconstruct()` to accept real `current`/`wind`/`input_envelope` (or an
   equivalent DI seam) so a live API-created case can reach real forcing — currently only reachable
   via standalone scripts.
3. Add `AdapterRegistry.create_live()` so `/health`/`/readiness` can report real adapter status.
4. Do not retrain, redesign PRATIVARTAN's core mathematics, or expand Track 2's architecture further
   without a new explicit mandate.
