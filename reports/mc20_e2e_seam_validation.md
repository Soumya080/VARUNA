# MC20 E2E Seam Validation

**Case:** MC20 / Taylor Energy (`data/gold/events/mc20_v0_1`)
**Generated:** 2026-08-29T20:27:15Z
**Overall status: READY**

This is an **integration smoke test**, not a scientific validation. It proves
every non-NETRA hop in the pipeline connects, exchanges the correct schema,
and propagates `EvidenceMode` honestly — it makes no claim about attribution
quality, forecast skill, or detection accuracy. NETRA has not yet produced a
real slick detection for this case, so the slick geometry used below is an
explicitly-labelled bounded synthetic placeholder, carried as
`EvidenceMode.SIMULATED` throughout — never reported as REAL.

All fixtures were kept small and bounded by design: `n_particles=20`,
`n_ensemble=4`, and 2 real AIS tracks streamed out of the 276MB bronze file
(not loaded in full). No NETRA inference, no production Φ sensitivity sweep,
no giant ensembles, and no GPU workloads were run.

## Seam-by-seam results

| # | Seam | Status | EvidenceMode |
|---|------|--------|--------------|
| 1 | `data/gold/events/mc20_v0_1` manifest loading | **READY** | — |
| 2 | Real ERA5 cube → `CubeBackedWindField` | **READY** | real |
| 3 | Real CMEMS cube → `CubeBackedCurrentField` | **READY** | real |
| 4 | Both fields → PRATIVARTAN forcing interface | **READY** | simulated |
| 5 | PRATIVARTAN output → `PhiField` | **READY** | simulated |
| 6 | `PhiField` → NYAYA input contract | **READY** | simulated |
| 7 | NYAYA output → `ValidityGate` input | **READY** | simulated |
| 8 | `ValidityGate` → ABHIYAN-compatible decision object | **READY** | simulated |
| 9 | PRAVAAH provider (real current field) → forecast object | **READY** | real |
| 10 | `EvidenceMode` propagation across every hop | **READY** | mixed |

### Detail

**1. Manifest loading — READY**
`event_id=mc20_2023-01-15`, `dataset_version=mc20_v0_1`. All four modalities
(`sar`, `ais`, `era5`, `cmems`) present; `ais/event_ais_join.json`,
`forcing/cmems_cube.json`, `forcing/era5_cube.json`, `sar/tile_records.json`,
`provenance/provenance.json` all resolve.

**2. Real ERA5 cube → `CubeBackedWindField` — READY**
Cube `era5-mc20-era5_mc20_2023-01-11_to_2023-01-17`,
`time_series_status=sufficient`. Raw `u10`/`v10` grid shape `(168, 17, 17)`
loaded from the real `.nc` file and fed through `CubeBackedWindField`.
Sample `velocity_at()` at the SAR footprint centroid returned
`(u=-0.30, v=3.50) m/s` — a real, non-fabricated wind vector.

**3. Real CMEMS cube → `CubeBackedCurrentField` — READY**
Cube `cmems-mc20-cmems_mc20_2023-01-11_to_2023-01-17`,
`time_series_status=sufficient`. Raw `uo`/`vo` grid shape `(133, 49, 49)`
after squeezing the file's length-1 `depth` axis (see "Defect fixed" below).
Sample `velocity_at()` returned `(u=0.123, v=0.004) m/s`.

**4. Both fields → PRATIVARTAN forcing interface — READY**
`run_backward_ensemble()` completed 4/4 members against the real
`CubeBackedCurrentField`/`CubeBackedWindField` pair — no member dropped, no
out-of-domain fallback triggered at this bounded scale. The advection
mathematics (`engine.py::advect_particles`) were not modified; this only
proves the real-forcing boundary feeds it correctly.

**5. PRATIVARTAN output → `PhiField` — READY**
`build_phi_field()` produced a valid `PhiField`
(`convergence_flag=not_converged`, `ensemble_completeness=1.00`). The
`not_converged` flag is an honest, expected result of the toy 4-member/20-
particle ensemble scale used here for GPU/time safety — not a defect.

**6. `PhiField` → NYAYA input contract — READY**
2 real AIS tracks (mmsi-identified, spatially matched to the SAR footprint
per `event_ais_join.json`) streamed out of the 276MB bronze file without a
full load, converted to `VesselTrack`/`AISPoint` contract objects, and
scored by `NyayaService.attribute()`. Result: `decision_state=latent_source`.
The attribution envelope stayed `simulated` even though the AIS track
envelope was `real` — correct monotonic-worsening behavior: a real input
cannot upgrade an already-simulated lineage.

**7. NYAYA output → `ValidityGate` input — READY**
`ValidityService.evaluate()` returned `gate_state=restricted`,
`allows_operational_action=False`. Failing checks: `phi_not_converged`,
`evidence_insufficient` (ensemble completeness/particle-loss thresholds,
pre-existing and unmodified), `phi_diagnostics_unavailable` (no sensitivity
sweep was run in this smoke test — the cheap default path leaves
`sensitivity=None`, exactly as ADR-0007 intends), `attribution_not_
distinguishable`. **No gate check was weakened to make this pass.**

**8. `ValidityGate` → ABHIYAN-compatible decision object — READY**
`AbhiyanService.plan_mission()` correctly read `gate_state=restricted` and
returned zero taskings — the fail-closed contract holds: a restricted gate
suppresses mission planning regardless of any prior confidence.

**9. PRAVAAH provider → real current field → forecast object — READY**
`CubeBackedPravaahProvider` (already implemented, `packages/varuna_pravaah/
cube_provider.py`) accepted the same real CMEMS-backed current field and
produced a `ForwardForecast` (`fcast-cube-mc20-seam-slick-0`, 1 landfall
prediction, trajectory written to a temp `.npz`).

**10. `EvidenceMode` propagation across every hop — READY**
```
forcing_envelope (ERA5+CMEMS real)   -> real
slick_envelope (bounded placeholder) -> simulated
reconstruction input (derived)       -> simulated
phi.envelope                         -> simulated
attribution.envelope                 -> simulated
gate_result.envelope                 -> simulated
```
Monotonic worsening held end to end: once the (honestly-labelled) simulated
placeholder entered the lineage, every downstream artifact reported
`simulated`, never `real`. No value was silently upgraded.

## Defect fixed (smallest integration gap only)

`packages/varuna_source_adapters/forcing_readers.py` had no function to load
the *raw* velocity arrays a `ForcingCube` describes — `CubeBackedCurrentField
.load_arrays()`/`CubeBackedWindField.load_arrays()` existed, but nothing in
the codebase yet called them against a real file. Added two narrow read-only
functions, `load_era5_wind_arrays()` and `load_cmems_current_arrays()`,
which open the same file the existing readers already validated and return
the `u`/`v` grids in the cube's own coordinate order. The real CMEMS files
carry a length-1 `depth` dimension (surface analysis product) that
`load_cmems_current_arrays()` squeezes explicitly (asserting depth size is
exactly 1 first — a genuinely multi-level file would raise, not silently
pick a level). No advection mathematics, contracts, or existing call sites
were touched.

## Files changed / created / deleted / moved / overwritten

- **Files changed:** `packages/varuna_source_adapters/forcing_readers.py`
- **Files created:** `scripts/mc20_e2e_seam_validation.py`,
  `reports/mc20_e2e_seam_validation.json`,
  `reports/mc20_e2e_seam_validation.md`
- **Files deleted:** 0
- **Files moved:** 0
- **Files overwritten:** 0

No file under `data/raw`, `data/bronze`, or `data/gold` was read-write
touched — every dataset access in this validation was read-only.

## What this does NOT prove

- Detection accuracy or attribution correctness — the slick geometry is a
  bounded synthetic placeholder, not a NETRA output.
- Production-scale gate behavior — `phi_not_converged` at 20
  particles/4 ensemble members is expected at this scale, and gate behavior
  at production scale (500/20, matching `PrativartanService.
  reconstruct_origin`'s defaults) is unverified here.
- Real AIS `SourceAdapter` wiring — tracks were read directly from the
  bronze file for this smoke test, not through `varuna_source_adapters.ais`
  (still a stub, pre-existing gap, unchanged by this validation).

## Next exact action

Run `PrativartanService.reconstruct_origin()` (or
`reconstruct_origin_with_sensitivity()`) at production particle/ensemble
scale against these same real ERA5/CMEMS cubes once NETRA's GPU load is
confirmed clear, to see whether `phi_not_converged` clears at real scale —
that is the one seam-adjacent question this smoke test cannot answer at
bounded size.
