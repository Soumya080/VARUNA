# MC20 Real E2E Acquisition — Final Report

**Pass:** Data Track execution phase — credential-configured acquisition,
completed across two rounds (SAR blocked/retried after an operator
account fix; ERA5 blocked/retried after a licence acceptance; CMEMS
succeeded on first authenticated attempt).
**Case (locked, unchanged):** MC20 / Taylor Energy, anchor 28.936°N, -88.970°W, Gulf of Mexico.
**Classification legend:** every factual claim below is tagged
`[MEASURED]` (re-derived from real data/response this pass),
`[DERIVED]` (computed from measured facts), `[DOCUMENTED]` (recorded
metadata), or `[BLOCKED]` (attempted, did not succeed, reason named).

---

## 1. Acquisition status

All three previously-missing modalities were acquired this pass:

| Modality | Result |
|---|---|
| CMEMS (uo/vo) | **`[MEASURED]` SUCCEEDED** — 133-timestep real series, first attempt after credential fix |
| ERA5 (u10/v10) | **`[MEASURED]` SUCCEEDED** — 168-timestep real series, after operator accepted the CDS licence |
| SAR (Sentinel-1 GRD) | **`[MEASURED]` SUCCEEDED** — full 1.74GB product, after operator corrected `CDSE_USERNAME` |

**All four required modalities (SAR, AIS, ERA5, CMEMS) are now genuinely REAL.**
`scripts/check_mc20_readiness.py` reports `REAL_E2E_READY = True` for
the data-closure scope this track owns (see §21 for why this is
distinct from full-system readiness).

## 2. Credential status (boolean only, no secrets)

All six credential variables are set in `.env` (gitignored, never
committed, never printed). Two required operator-side fixes discovered
during this pass, both resolved without this session ever seeing the
corrected values:

- **CDSE (Copernicus Data Space)**: initial value returned a reproducible
  `401 Unauthorized`. Operator identified the *username* was wrong,
  corrected it directly in `.env`; re-test returned `200`.
- **CDS API (ERA5)**: credentials authenticated correctly throughout —
  the block was `403 required licences not accepted`. Operator accepted
  the licence on the CDS website; the identical request then succeeded
  (`status: accepted → running → successful`).
- **Copernicus Marine (CMEMS)**: worked on the first authenticated
  attempt this pass.

`.env`'s `KEY = value` / `KEY= value` formatting (with stray spaces)
broke plain `source` twice this pass; fixed both times with a
structural `sed` normalization that never touches the values
themselves, only whitespace around `=`.

## 3. SAR status

**`[MEASURED]` REAL.** Product:
`S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE`,
UUID `6fc676ba-b961-5bfc-9211-8076f8f1481c`.

- Downloaded size: 1,741,458,044 bytes — **exact match** to the expected size.
- SHA-256 (of the downloaded zip): `68f5c1f4a35fc64f92f07ee595036d668ef87582bfeaa69b1b8fe86742857d96`.
- Extracted to `data/raw/sentinel1_grd/mc20_2023-01-15/`, real SAFE structure confirmed: `manifest.safe`, `measurement/` (VV+VH GeoTIFFs, 25899×16734 px, 16-bit, ~867MB each), `annotation/` (per-polarization XML + `calibration/calibration-*.xml` + `calibration/noise-*.xml`), `preview/`, `support/`.
- **Independent cross-check**: the product's own annotation `azimuthTime` for its first geolocation grid point reads `2023-01-15T00:02:06.898342` — matches `T_SAR` used throughout every MC20 report to the microsecond, confirmed from the product's own metadata rather than only the catalog filename.

## 4. AIS status

`[MEASURED]`, unchanged: 304,960 real records, 535 unique vessels, 530
cleaned tracks, source `data/raw/ais/2023-01-15/AIS_2023_01_15.csv`.
Not redownloaded, not duplicated, not modified.

## 5. ERA5 status

**`[MEASURED]` REAL.** `data/raw/era5_mc20/era5_mc20_2023-01-11_to_2023-01-17.nc`:

- SHA-256: `8db79ceb5b3aa417d688a0d75e01bd6e5f2f0d9119d6280d1beed5c1d8d8e399`.
- 168 real hourly timesteps, `2023-01-11T00:00` to `2023-01-17T23:00` — spans the full requested week.
- Region lat[27,31] lon[-91,-87] — exact match to request.
- `u10` range [-5.08, 14.39] m/s, `v10` range [-12.18, 10.84] m/s — physically plausible Gulf of Mexico winter wind, no NaN, no Inf.
- Real value at the anchor's nearest grid cell (t0): `u10=0.279 m/s, v10=2.789 m/s`.

**Engineering note**: `xarray.open_dataset()` hung indefinitely on this
exact file (an engine-detection issue, reproduced consistently, not a
data problem — the file opens instantly via `netCDF4` directly).
`check_mc20_readiness.py`'s ERA5/CMEMS checks and their spatial/temporal
intersection helpers were switched to `netCDF4` for this reason.

## 6. CMEMS status

`[MEASURED]` REAL, unchanged from the prior round of this pass: 133
real hourly timesteps, `2023-01-11T12:00` to `2023-01-17T00:00`, region
lat[27,31] lon[-91,-87], `uo`/`vo` present, 26.4% NaN (coastal/shelf
masking, not a query error), no Inf. SHA-256:
`06163c96bf97b8fd2c34fb7b18720c3219d3bd1824f428dfb56ce24a5b0b9130`.

## 7. Spatial alignment

`[MEASURED]`, re-derived from the real files on disk, not asserted:

- SAR anchor point (-88.970, 28.936) falls inside **both** the ERA5 and CMEMS grid bounds.
- SAR↔AIS: non-empty (304,960 points in-swath, 38,244 within ±3h, closest 3.26km).
- **Four-way (SAR ∩ AIS ∩ ERA5 ∩ CMEMS): `NON-EMPTY` — all four modalities real and spatially intersecting.** This was `EMPTY` at the start of this pass.

## 8. Temporal alignment

`[MEASURED]`:

- T_SAR = `2023-01-15T00:02:06.898Z`, independently confirmed by the SAR product's own annotation metadata (§3).
- ERA5 window (`2023-01-11T00:00`–`2023-01-17T23:00`) **CONTAINS** T_SAR.
- CMEMS window (`2023-01-11T12:00`–`2023-01-17T00:00`) **CONTAINS** T_SAR.
- AIS: closest real point at `2023-01-15T00:19:04Z`, `+16m57s`/`3.26km` from T_SAR/anchor.
- Backward transport window: still no case-specific value — `NetraInferenceService.detect()` remains a mock stub (§11). Any 16–84h figure quoted elsewhere is an explicitly labeled planning bound, not a scientific estimate.

## 9. SAR preprocessing status

**`[MEASURED]` VALIDATED against the real SAFE product**, not just the
synthetic fixture. `scripts/validate_mc20_sar_calibration.py` (new this
pass):

1. Located the MC20 anchor's real pixel position via the product's own
   `geolocationGridPoint` list (nearest real grid point: line=8036,
   pixel=19425, lat=28.995, lon=-88.970 — ~6.6km from the exact anchor,
   the nearest of only 210 grid points across the whole scene).
2. Read a real 1536×1536 DN window centered there directly from both
   measurement TIFFs (via file-seek + `numpy`, after PIL's per-strip
   decode proved extremely slow for a windowed read on this
   one-row-per-strip product — see §23).
3. Ran the **actual, unmodified** `sentinel1_grd_calibration.py`
   functions: `parse_calibration_lut`, `_interpolate_lut_to_grid`
   (shifted into the crop's local frame), `apply_netra_normalization`
   (using the frozen Gold v0.2 bounds read directly from the manifest),
   `tile_512`.
4. Result: VV DN [9,2891] → dB [-36.14,14.05]; VH DN [2,937] → dB
   [-49.15,4.25]; normalized [2,1536,1536] range [0,1], **no NaN, no
   Inf**; 9 real 512×512 tiles produced, matching the Gold v0.2 tiling
   convention exactly.

Full result: `reports/mc20_sar_calibration_validation.json`. New tests:
`tests/unit/test_mc20_sar_calibration_real.py` (5 tests, skip cleanly
if the SAFE product is absent).

## 10. Event Gold status

`[BLOCKED]`, correctly not attempted this pass. All four modalities are
now real, so the precondition for building
`data/gold/varuna_event_v0_1/` is satisfied — but the task explicitly
scoped Event Gold construction as a separate step, not to be built
opportunistically inside the same pass as acquisition. Flagged as the
next concrete action (§14).

## 11. NETRA dependency status

`NETRA_REAL_INFERENCE = BLOCKED`, unchanged. `NetraInferenceService.detect()`
still returns a hardcoded mock `SlickDetection`. Not touched, not
inspected further this pass beyond the standing confirmation. NETRA's
training process (PIDs 1496/58256, plus dataloader worker forks) was
health-checked repeatedly throughout this pass and found unchanged and
undisturbed every time, including immediately before this report.

## 12. Track 2 dependency status

**Status changed since the prior report, discovered (not modified) this
pass**: Track 2 landed commit `8c257e0` ("ratify Phi sensitivity
normalization, remove PHI_DIAGNOSTICS_UNAVAILABLE block") — the
normalization-convention decision that previously left `SensitivityBlock`
permanently `None` has been ratified, with a real zero-free-parameter
formula (`sensitivity = centroid_shift_km / effective_radius_km`).
This is Track 2's own work, not independently re-verified end-to-end by
this pass — reported factually because it changes §21's checklist
entry, not claimed as fixed by this track.

## 13. Remaining blockers

1. **NETRA real inference**: mock stub, pre-existing, out of this track's scope.
2. **PRATIVARTAN real forcing path**: the real ERA5/CMEMS files exist now, but `CubeBackedCurrentField`/`CubeBackedWindField` have not been run against them end-to-end this pass — that integration step, not the data, is what's missing.
3. **Event Gold**: not built (§10) — correctly deferred, not a blocker in the sense of being stuck, just not yet done.
4. **Validity gate**: Track 2's Phi sensitivity path was recently ratified (§12) but not independently confirmed satisfied by this track.

## 14. Exact next actions

1. Run `CubeBackedCurrentField`/`CubeBackedWindField` against the real
   `era5_mc20`/`cmems_mc20_timeseries` files to prove the forcing seam
   works end-to-end with real data (currently only tested against
   synthetic cubes).
2. Build Event Gold (`data/gold/varuna_event_v0_1/{sar,ais,era5,cmems,metadata,provenance,diagnostics}/`
   + manifest) now that all four modalities are genuinely real.
3. Confirm with Track 2 whether the ratified Phi sensitivity formula is
   now actually populating `SensitivityBlock` (not just designed) for
   the validity gate.
4. NETRA real inference remains the one blocker with no near-term fix
   available from this track — out of scope, flagged for whichever
   track owns `varuna_netra/inference.py`.

## 15. Files created (this round)

- `scripts/validate_mc20_sar_calibration.py`
- `tests/unit/test_mc20_sar_calibration_real.py`
- `reports/mc20_sar_calibration_validation.json`
- `data/raw/sentinel1_grd/mc20_2023-01-15/` (the real SAFE product)
- `data/catalog/acquisition/{era5_mc20,sentinel1_grd_mc20}.json`

## 16. Files modified (this round)

- `.env` (credential corrections by the operator; not committed, not read into any report)
- `scripts/check_mc20_readiness.py` — SAR/ERA5/CMEMS checks now report real validated content; **fixed a genuine bug**: unclosed `netCDF4.Dataset` handles caused a real Windows access-violation crash when multiple checks ran in one pytest process — all four open sites now use `with` context managers (§23).
- `data/catalog/{checksums,dataset_inventory,dataset_paths}.json` — additive SAR/ERA5 entries, zero existing entries touched (verified by count each time).
- `reports/mc20_readiness.json`, `reports/mc20_readiness_final.json`, this file.

## 17. Files deleted

**0.**

## 18. Files renamed

**0.**

## 19. Files moved

**0.**

## 20. Checksums

| File | SHA-256 |
|---|---|
| SAR product zip | `68f5c1f4a35fc64f92f07ee595036d668ef87582bfeaa69b1b8fe86742857d96` |
| ERA5 nc | `8db79ceb5b3aa417d688a0d75e01bd6e5f2f0d9119d6280d1beed5c1d8d8e399` |
| CMEMS nc | `06163c96bf97b8fd2c34fb7b18720c3219d3bd1824f428dfb56ce24a5b0b9130` |

## 21. Provenance

All three new acquisition records in `data/catalog/acquisition/`:
product/dataset ID, variables, region, time window, download timestamp,
size, checksum, destination path. Credential source class recorded as
environment variables, never the values.

## 22. Scientific limitations

- The SAR calibration validation covers a 1536×1536 window around the
  anchor, not the full ~25899×16734 scene — sufficient to prove the
  pipeline is correct on real data, not a full-scene product.
- Thermal noise removal, terrain correction, and speckle filtering
  remain **NOT IMPLEMENTED** (unchanged from the prior pass) —
  classified per §11's original schema:
  - Thermal noise removal: **SCIENTIFIC FOLLOW-UP** (noise LUTs are present in the real product, `annotation/calibration/noise-*.xml`, confirmed this pass — the data to implement this exists, the implementation does not).
  - Terrain correction: **NOT REQUIRED FOR CURRENT BASELINE** (GRD is ellipsoid-projected, consistent with how Zenodo's training imagery is delivered — not a new gap this introduces).
  - Speckle filtering: **SCIENTIFIC FOLLOW-UP** (not determined whether Zenodo's tiles have this applied by their original authors; not replicated here either way).
- The nearest real geolocation grid point to the anchor is ~6.6km away (210 grid points span the whole scene) — the calibration window is centered there, not on an exactly-interpolated anchor pixel. Fine for pipeline validation; a production tiling pass should interpolate properly between grid points rather than snap to nearest.

## 23. Engineering limitations

- **A real bug was found and fixed this pass**: `check_mc20_readiness.py` opened `netCDF4.Dataset` objects without closing them; running multiple checks against the same files in one pytest process caused a genuine Windows access-violation crash (not a flaky timeout — a real segfault, confirmed reproducible, confirmed fixed by switching all four open sites to `with` context managers, confirmed fixed by rerunning the exact crashing test).
- `xarray.open_dataset()` was observed to hang indefinitely and unpredictably on both the ERA5 and CMEMS files across separate runs in this environment; `netCDF4` opens both instantly. All gate-script reads now use `netCDF4` directly.
- `PIL.Image.crop()` was extremely slow reading a windowed region from the SAR measurement TIFF (each row stored as its own separate strip — 16,734 strips for a 16,734-row image — makes PIL's per-strip Python-level decode loop slow for windowed access). Replaced with a direct file-seek + `numpy.frombuffer` read, verified against the product's own strip offsets (uncompressed, little-endian, confirmed) — near-instant.
- `rasterio` import also hung in this environment during initial diagnosis; not used — deliberately avoided in favor of `netCDF4`/direct TIFF reads for exactly this reason. Also correct for this product type regardless: Sentinel-1 GRD measurement TIFFs are not georeferenced GeoTIFFs — geolocation comes from the annotation XML's `geolocationGrid`, which `rasterio`'s CRS machinery would not have used anyway.
- `pytest` itself appeared to hang on a full-file run at one point during this pass; isolating to individual tests showed every test passed instantly and the full file passed cleanly moments later — assessed as a transient resource-contention spike, not a reproducible issue (distinct from the real netCDF4 crash bug, which *was* reproducible and *was* fixed).

---

## Final decision

**REAL_E2E_PARTIAL** — 11/15 readiness-checklist items true (`reports/mc20_readiness_final.json`).

The distinction that matters: `scripts/check_mc20_readiness.py`'s own
`REAL_E2E_READY` field is **`True`** — that gate covers exactly what
this track owns (SAR/AIS/ERA5/CMEMS all real, spatially/temporally
verified, no locked-data contamination). The **broader system**
checklist in this report additionally requires Event Gold, NETRA real
inference, an end-to-end PRATIVARTAN forcing run, and Track 2's
validity-gate confirmation — none of which are this track's to build,
and none of which were silently assumed done. The data side of the
MC20 case is closed. What remains is integration work belonging to
other parts of the system.
