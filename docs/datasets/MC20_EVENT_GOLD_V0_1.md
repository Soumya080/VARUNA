# MC20 Event Gold v0.1

**Path:** `data/gold/events/mc20_v0_1/`
**Purpose:** inference and E2E validation. **NOT a training dataset** — no oil labels exist for this scene and none are fabricated here.
**Status:** built, validated, frozen. `EVENT_GOLD_READY = True` (`reports/mc20_event_gold_readiness.json`).

---

## Event definition

| | |
|---|---|
| Case | MC20 / Taylor Energy |
| Anchor | 28.936°N, -88.970°W (Gulf of Mexico) |
| T_SAR | `2023-01-15T00:02:06.898Z` |
| Dataset version | `mc20_v0_1` |
| Processing git commit | `cf0e21307afe519094c04eea35bddeba96c77702` |
| Builder | `scripts/build_mc20_event_gold.py` |
| Readiness gate | `scripts/check_mc20_event_gold_readiness.py` |

## Exact source products

| Modality | Product | Checksum |
|---|---|---|
| SAR | `S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE`, UUID `6fc676ba-b961-5bfc-9211-8076f8f1481c` | `68f5c1f4a35fc64f92f07ee595036d668ef87582bfeaa69b1b8fe86742857d96` (zip) |
| AIS | NOAA MarineCadastre `AIS_2023_01_15.csv`, MC20 bbox extraction | referenced, not independently re-hashed (289MB bronze extraction) |
| ERA5 | `reanalysis-era5-single-levels:10m_wind`, NetCDF | `8db79ceb5b3aa417d688a0d75e01bd6e5f2f0d9119d6280d1beed5c1d8d8e399` |
| CMEMS | `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` | `06163c96bf97b8fd2c34fb7b18720c3219d3bd1824f428dfb56ce24a5b0b9130` |

## Acquisition timestamps

- SAR: `2023-01-15T00:02:06.898000+00:00` — independently confirmed by the product's own annotation `azimuthTime`, not just its filename.
- AIS: full day `2023-01-15`.
- ERA5: `2023-01-11T00:00` to `2023-01-17T23:00` (168 hourly steps).
- CMEMS: `2023-01-11T12:00` to `2023-01-17T00:00` (133 hourly steps).

## Spatial bounds

| Modality | bbox (lon, lat) |
|---|---|
| SAR real scene footprint | `[-91.101, 27.953]` to `[-88.173, 29.877]` (derived from all 210 real geolocationGridPoints, not assumed) |
| ERA5 / CMEMS | `[-91.0, 27.0]` to `[-87.0, 31.0]` |

## Temporal bounds

- ERA5 and CMEMS windows both **contain** T_SAR (verified, not asserted).
- AIS: 320/530 tracks temporally matched (within `AIS_WINDOW_BEFORE_HOURS=48` / `AIS_WINDOW_AFTER_HOURS=6`, the project's existing real config, not invented for this build).

## SAR preprocessing

Pipeline (unmodified `sentinel1_grd_calibration.py`): SAFE → real DN window (direct file-seek read, 1536×1536 centered on the anchor's nearest real geolocation grid point) → `parse_calibration_lut` → `_interpolate_lut_to_grid` (shifted into the crop's local frame) → `calibrate_to_db` (DN → sigma0 → dB) → `apply_netra_normalization` (FROZEN `netra-norm-v0.2-nodata-excluded` bounds, read directly from `data/manifests/netra_gold_v0_2.json`, never recomputed) → `tile_512`.

Result: **9 real `[2,512,512]` float32 tiles** (VV, VH only — no third channel), zero NaN/Inf, normalized range `[0,1]`. VV dB range `[-36.14, 14.05]`, VH dB range `[-49.15, 4.25]`.

**Tile geolocation is approximate**: bboxes come from the nearest of the scene's 210 sparse geolocationGridPoints per tile corner, not bilinear-exact interpolation. Because the grid spacing is coarser than a single 512px tile, 3 of 9 tiles had all 4 corners collapse to the same grid point; these were padded by half the tile's derived angular footprint (documented per-tile in `tile_records.json`'s provenance notes). Adequate for inference/validation, not claimed adequate for sub-pixel geolocation.

Thermal noise removal, terrain correction, and speckle filtering remain **not implemented** (unchanged from the calibration-validation pass) — noise LUTs exist in the real product (`annotation/calibration/noise-*.xml`) but are not applied.

## AIS processing

530 real tracks from the existing MC20 bronze extraction (`data/bronze/ais/mc20_2023-01-15_tracks.json`) — **referenced, not copied** (the 289MB file stays where it is; only a derived, much smaller join summary is materialized).

Per track: tested against the real SAR scene footprint (spatial match) and the real `[T_SAR-48h, T_SAR+6h]` window (temporal match), computed independently via haversine distance — **425/530 spatially matched, 320/530 temporally matched**, 210 temporally unavailable. A spatial candidate is never silently promoted to a temporal match.

Two distinct "closest" figures are reported, deliberately not conflated:
- **Closest by pure distance, any time**: 60m (MMSI 367640910), but 23 hours from T_SAR — informational only, not scientifically meaningful for attribution.
- **Closest *temporally matched***: 3.2554km, +16m57s (MMSI 368181750, "HELEN") — this **exactly reproduces** the prior data-track report's finding, verified fresh from raw data in this pass, not re-asserted.

## ERA5 processing

Read via a new netCDF4-based reader (`packages/varuna_data_eng/preprocessing/mc20_forcing_netcdf4.py::read_era5_netcdf4`) producing the standard `ForcingCube` contract (reused, not duplicated — same schema as `varuna_source_adapters.forcing_readers.read_era5_grib`). `xarray` was avoided: it hung indefinitely and reproducibly on this exact file in this environment (an engine-detection issue, not a data problem — confirmed by netCDF4 opening it instantly); `read_era5_grib` itself doesn't apply regardless, since it requires GRIB1+cfgrib and this file is NetCDF.

168 hourly timesteps, `time_series_status=sufficient`, spatial/temporal containment of the SAR anchor/T_SAR both verified.

## CMEMS processing

Same netCDF4-based approach (`read_cmems_netcdf4`), same reasons. 133 hourly timesteps, `time_series_status=sufficient`, spatial/temporal containment verified. 26.4% NaN over the grid (coastal/shelf masking, not a query error — established in the prior acquisition pass, unchanged here).

## Alignment

Four-way spatial intersection (SAR ∩ AIS ∩ ERA5 ∩ CMEMS): **non-empty**, verified — 425 AIS tracks spatially match the real SAR footprint, and both forcing cubes' grids contain the SAR anchor point. Full detail in `diagnostics/alignment.json`.

## Provenance

`provenance/provenance.json` traces every derived artifact to its immutable raw source by path + checksum, plus the exact git commit this build ran at. No raw file was copied except where explicitly noted (SAR tiles are cut from, not copies of, the SAFE product; the AIS join is a derived summary, not a copy of the 289MB bronze file).

## Limitations

**Scientific:**
- SAR calibration covers a 1536×1536 window around the anchor, not the full ~25899×16734 scene.
- Tile geolocation is nearest-grid-point-approximate (see above), not bilinear-exact.
- No case-specific NETRA detection age prior exists — this corpus does not attempt to fix that; PRATIVARTAN transport-window figures used elsewhere remain labeled planning bounds.
- Thermal noise / terrain correction / speckle filtering not implemented.

**Engineering:**
- Import order matters on Windows in this environment: `netCDF4` imported before `varuna_contracts`/`varuna_data_eng` pydantic schema modules causes those imports to hang indefinitely and reproducibly (confirmed by isolating both directions) — all MC20 forcing code imports schemas first. Documented in `mc20_forcing_netcdf4.py`'s module docstring.
- `scipy.interpolate.RegularGridInterpolator` with `fill_value=None` (extrapolation mode) took 0.03s–2.5s depending on system load in this pass — legitimately somewhat slow, not a hang, but can appear stalled under NETRA's fluctuating resource contention.
- The build failed twice during development on a genuine bug (degenerate `BBox` when nearest-grid-point lookups for a tile's 4 corners collapsed to a single point) before the epsilon-pad fix — not silently worked around, fixed and documented.

## Known unavailable fields

- AIS `bbox` in the manifest's `modalities.ais` block is `null` — AIS doesn't have a single fixed bbox the way a raster does; per-track spatial matching is in `ais/event_ais_join.json` instead.
- SAR tile bboxes are approximate (see above), not exact.
- No oil/not-oil labels anywhere in this corpus — deliberate, per task scope.

## Exact generation command

```
python scripts/build_mc20_event_gold.py
python scripts/check_mc20_event_gold_readiness.py
```

Both are read-only with respect to raw data; the builder refuses to run again if `data/gold/events/mc20_v0_1/` already exists and is non-empty (proven by `tests/unit/test_mc20_event_gold.py::test_builder_refuses_to_overwrite_existing_event_gold`). A defect found later means `mc20_v0_2`, never an in-place edit of this version.

## NETRA training isolation

Every tile's `split` field is `"mc20_event_inference"` — deliberately outside `NetraGoldDataset.VALID_SPLITS = ("train","val","test")`. Proven structurally, not just documented: calling `NetraGoldDataset(manifest_path=<this manifest>, split="mc20_event_inference")` raises `ValueError` (`tests/unit/test_mc20_event_gold.py::test_netra_gold_dataset_rejects_this_manifest`), and `packages/varuna_netra/dataset/gold.py` contains no glob/listdir/walk call at all — membership is manifest-only by construction, verified by source inspection in the same test file.

## Locked-evaluation isolation

Zenodo Part III and ESSD are referenced nowhere in this corpus — verified against the real `locked_dataset_ids()` guard (`tests/unit/test_mc20_event_gold.py::test_no_locked_evaluation_dataset_referenced`), not just asserted in the manifest.
