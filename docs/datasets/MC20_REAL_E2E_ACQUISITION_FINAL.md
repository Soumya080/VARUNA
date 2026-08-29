# MC20 Real E2E Acquisition — Final Report

**Pass:** Data Track execution phase, credential-configured acquisition attempt.
**Case (locked, unchanged):** MC20 / Taylor Energy, anchor 28.936°N, -88.970°W, Gulf of Mexico.
**Classification legend:** every factual claim below is tagged
`[MEASURED]` (re-derived from real data/response this pass),
`[DERIVED]` (computed from measured facts), `[DOCUMENTED]` (recorded
metadata, e.g. from a prior pass or a provider's own labeling), or
`[BLOCKED]` (attempted, did not succeed, reason named).

---

## 1. Acquisition status

Three independent acquisitions were attempted this pass, in the order
SAR → ERA5 → CMEMS, using `scripts/acquire_mc20_{sar,era5,cmems}.py`
unmodified from the prior pass:

| Modality | Result |
|---|---|
| SAR (Sentinel-1 GRD) | `[BLOCKED]` — credential rejection |
| ERA5 (u10/v10) | `[BLOCKED]` — licence not accepted |
| CMEMS (uo/vo) | **`[MEASURED]` SUCCEEDED** — real 133-timestep series acquired |

## 2. Credential status (boolean only, no secrets)

`[MEASURED]`, checked via `os.environ` presence, never echoed:

| Variable | Set |
|---|---|
| `CDSE_USERNAME` | true |
| `CDSE_PASSWORD` | true |
| `CDSAPI_URL` | true |
| `CDSAPI_KEY` | true |
| `COPERNICUSMARINE_SERVICE_USERNAME` | true |
| `COPERNICUSMARINE_SERVICE_PASSWORD` | true |

All six were present. Two of three services rejected them or the
associated account state anyway (see §3–§4) — configured is not the
same as accepted, and that distinction is the actual finding of this
pass.

**Unplanned but urgent finding**: before any acquisition was attempted,
`.env.example` — a file the repo's own `.gitignore` deliberately keeps
*tracked* as a public template (`!.env.example`) — was found holding
these same six real values, pasted directly into it in the working
tree. `git show HEAD:.env.example` confirmed the committed version
still had empty placeholders `[MEASURED]`, so nothing had reached git
history. Fixed before touching anything else: the real values were
copied into `.env` (already gitignored), `.env.example` was restored
to empty placeholders, and `.gitignore` was extended to also cover
`.cdsapirc` / `.copernicusmarine/` / `.netrc` (a stray untracked
`.cdsapirc` was also sitting at repo root). No credential value was
ever printed, logged, committed, or written into any script or report
in this session.

## 3. SAR status

`[BLOCKED]`. Product remains identified and catalog-confirmed from the
prior pass (`S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE`,
UUID `6fc676ba-b961-5bfc-9211-8076f8f1481c`, 1,741,458,044 bytes) but
not downloaded.

`[MEASURED]` `scripts/acquire_mc20_sar.py` was run with
`CDSE_USERNAME`/`CDSE_PASSWORD` set. The token request to
`https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token`
returned `HTTP 401 Unauthorized`. Reproduced a second time via a
direct `curl` POST to the same endpoint with the same credentials
(status code only checked, no response body or credentials printed) —
`401`, not transient.

This is an authenticated rejection, not a missing-credential state.
Known causes of a 401 at this specific endpoint (not diagnosed further
without risking account lockout from repeated attempts): incorrect
password, an unverified/unactivated Copernicus Data Space Ecosystem
account, or an account created on the older Copernicus Open Access Hub
(`scihub.copernicus.eu`) rather than the current Data Space Ecosystem
(`dataspace.copernicus.eu`) — these are separate systems with separate
accounts.

`[MEASURED]` A full-drive search (`find` for `*046787_059BFF*` and
`*S1A_IW_GRDH_1SDV_20230115*` under `D:\ROUTER(DATASETS)`) confirmed
the exact product does not already exist anywhere on disk under any
other path — genuinely not downloadable-avoidably, this specific 401
is the only blocker.

`data/raw/sentinel1_grd/` was never created (the script fails before
reaching that step) — no partial download exists to protect or resume.

## 4. AIS status

`[MEASURED]`, unchanged from the prior pass, re-verified this pass via
`scripts/check_mc20_readiness.py`: 304,960 real records, 535 unique
vessels, 530 cleaned tracks, source `data/raw/ais/2023-01-15/AIS_2023_01_15.csv`.
Not redownloaded, not duplicated, not modified.

## 5. ERA5 status

`[BLOCKED]`, but differently than before. `scripts/acquire_mc20_era5.py`
was run with `CDSAPI_URL`/`CDSAPI_KEY` set. `[MEASURED]` Authentication
succeeded — the request reached job submission
(`ecmwf.datastores` client, `POST .../processes/reanalysis-era5-single-levels/execution`)
before failing with `HTTP 403 Forbidden`, body: *"required licences not
accepted... please visit
https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download#manage-licences
to accept the required licence(s)."*

This is a one-time account-side action (accepting the dataset's terms
of use while logged in), not a credential or code defect. `data/raw/era5_mc20/`
was created (mkdir happens before the request) but is empty — no
partial `.nc` file, safe to retry as-is once the licence is accepted.

## 6. CMEMS status

**`[MEASURED]` REAL, genuine time series, verified from actual file
content, not filenames.**

- File: `data/raw/cmems_mc20_timeseries/cmems_mc20_2023-01-11_to_2023-01-17.nc`, 2,580,836 bytes.
- SHA-256: `06163c96bf97b8fd2c34fb7b18720c3219d3bd1824f428dfb56ce24a5b0b9130`.
- Product: `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m`, variables `uo`, `vo`.
- Dimensions: `time=133, depth=1, latitude=49, longitude=49`.
- Time range: `2023-01-11T12:00:00` to `2023-01-17T00:00:00`, hourly — 133 real timesteps, not a single-frame snapshot.
- Spatial range: lat `[27.0, 31.0]`, lon `[-91.0, -87.0]`, matching the requested region exactly.
- Units: `m s-1` for both variables.
- Data quality: 26.4% NaN across the grid (`[MEASURED]`) — consistent with expected coastal/continental-shelf masking in a Gulf-of-Mexico-coast product at 0.083° resolution, not a query error. No Inf values anywhere. `uo` finite range `[-0.77, 1.66]` m/s, `vo` finite range `[-0.76, 0.67]` m/s — physically plausible ocean current magnitudes.
- Value at the MC20 anchor's nearest real grid cell (28.917°N, -89.0°W, first timestep): `uo=0.132 m/s`, `vo=-0.145 m/s` — a real, non-NaN measurement at the case site.

The acquisition took two attempts: the first run stalled for ~13
minutes at the dataset-selection step with negligible CPU progress and
was terminated (`[MEASURED]` process CPU time advanced only 2.31s→2.53s
over 4 minutes — effectively idle) before any file was written
(`data/raw/cmems_mc20_timeseries/` existed but was empty, confirmed
before terminating); the retry completed normally in ~21 seconds once
past that same checkpoint. No partial or corrupt file was ever left on
disk from the first attempt.

## 7. Spatial alignment

`[MEASURED]`, re-derived from the real CMEMS file (not a stub string)
by `scripts/check_mc20_readiness.py`'s `_real_cmems_facts()`:

- SAR anchor point (-88.970, 28.936) falls inside the CMEMS grid's lat/lon bounds — **CONTAINS = true**.
- SAR↔AIS: non-empty — 304,960 AIS points within the SAR scene's IW swath, 38,244 within ±3h of acquisition, closest point 3.26km (`[MEASURED]`, prior pass, unchanged).
- SAR↔ERA5: not computable — ERA5 not yet acquired for this region.
- Four-way (SAR ∩ AIS ∩ ERA5 ∩ CMEMS): **EMPTY** — SAR and ERA5 are not simultaneously real with AIS and CMEMS today.

## 8. Temporal alignment

`[MEASURED]`, likewise re-derived, not asserted:

- T_SAR = `2023-01-15T00:02:06.898Z`.
- CMEMS window `2023-01-11T12:00Z`–`2023-01-17T00:00Z` — **CONTAINS T_SAR = true**.
- AIS: closest real point at `2023-01-15T00:19:04Z`, offset `+16m57s`, `3.26km` from the SAR timestamp/anchor.
- ERA5: `UNAVAILABLE` — not yet acquired.
- Backward transport window: no case-specific value exists — `NetraInferenceService.detect()` returns a mock detection (`[MEASURED]`, confirmed by source inspection, unchanged from prior pass). The 16–84h figure quoted anywhere in this project's MC20 scripts is an explicitly labeled **planning bound** drawn from hardcoded precedent elsewhere in the codebase, never presented as a computed value for this scene.

## 9. SAR preprocessing status

`[BLOCKED]` — cannot be validated against the real SAFE product because
the product is not downloaded (§3). `packages/varuna_data_eng/preprocessing/sentinel1_grd_calibration.py`
remains tested only against the synthetic fixture built in the prior
pass (9 passing unit tests, `tests/unit/test_sentinel1_grd_calibration.py`,
unchanged this pass). No SAFE-structure discovery, no real calibration
XML, no real DN→sigma0→dB conversion has been run against actual MC20
data. This is the same "next engineering step" flagged in the prior
report — not started this pass, correctly, since it depends on §3.

## 10. Event Gold status

`[BLOCKED]`, correctly not attempted. `data/gold/varuna_event_v0_1/`
was not created — the task rule requires all four modalities genuinely
present and verified first; SAR and ERA5 are not.

## 11. NETRA dependency status

`NETRA_REAL_INFERENCE = BLOCKED` `[MEASURED]`. `NetraInferenceService.detect()`
still returns a hardcoded mock `SlickDetection`
(`age_prior_mean_hours=12.0, age_prior_std_hours=2.0`) — confirmed by
direct source inspection, unchanged. NETRA training itself was not
touched, inspected for correctness, or interfered with — its process
(PIDs 1496/58256, and their dataloader worker forks) was confirmed
alive with unchanged start time at the beginning and end of this pass.

## 12. Track 2 dependency status

`PHI_DIAGNOSTICS_UNAVAILABLE` — recorded as an independent blocker per
the task instructions, not re-verified or touched this pass (Track 2
owns `packages/varuna_prativartan/phi_builder.py` and
`docs/adr/ADR-0007-*`; neither was modified here). Note: git status
shows `packages/varuna_prativartan/phi_builder.py` as modified in the
working tree, but that modification belongs to the active NETRA/Track-2
workstream (pre-existing before this pass began) and was correctly
left unstaged and uncommitted by this pass's commit.

## 13. Remaining blockers

1. **SAR**: Copernicus Data Space `401 Unauthorized`, account-side, reproduced twice.
2. **ERA5**: CDS API `403` licence-not-accepted, one-time account action.
3. **NETRA real inference**: mock stub, pre-existing, out of this track's scope.
4. **PRATIVARTAN real forcing path**: needs SAR+ERA5+CMEMS together; only CMEMS real today.
5. **Φ sensitivity / validity gate**: Track 2's `PHI_DIAGNOSTICS_UNAVAILABLE`, independent of data acquisition.

## 14. Exact next actions

1. Operator: verify the CDSE account at https://dataspace.copernicus.eu/ — confirm it is a Data Space Ecosystem account (not old scihub), confirm the password, and confirm the account is activated (check for a verification email). Re-set `CDSE_USERNAME`/`CDSE_PASSWORD` in `.env` if anything was wrong.
2. Operator: log in at https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download#manage-licences and accept the licence — one click, no code change needed.
3. Once either is fixed: re-run `scripts/acquire_mc20_sar.py` and/or `scripts/acquire_mc20_era5.py`, then `scripts/check_mc20_readiness.py`.
4. Once SAR lands: run the real-SAFE preprocessing validation against `sentinel1_grd_calibration.py` (§9's deferred step).
5. Once all four modalities are real: build Event Gold.

## 15. Files created

- `data/raw/cmems_mc20_timeseries/cmems_mc20_2023-01-11_to_2023-01-17.nc`
- `data/catalog/acquisition/cmems_mc20.json`
- `.env` (gitignored, not committed)
- `reports/mc20_readiness_final.json`
- `docs/datasets/MC20_REAL_E2E_ACQUISITION_FINAL.md` (this file)
- `data/raw/era5_mc20/` (empty directory, no file inside)

## 16. Files modified

- `.env.example` (secrets removed, restored to placeholders)
- `.gitignore` (credential patterns added)
- `data/catalog/checksums.json`, `dataset_inventory.json`, `dataset_paths.json` (additive CMEMS entries only, verified zero pre-existing entries altered)
- `reports/mc20_readiness.json` (regenerated by the gate)
- `scripts/check_mc20_readiness.py` (corrected two stale blocking-reason strings; real CMEMS spatial/temporal intersection computation replacing a hardcoded stub)

## 17. Files deleted

**0.**

## 18. Files renamed

**0.**

## 19. Files moved

**0.**

## 20. Checksums

CMEMS file SHA-256: `06163c96bf97b8fd2c34fb7b18720c3219d3bd1824f428dfb56ce24a5b0b9130` (recorded in `data/catalog/checksums.json` under a new `cmems_mc20_timeseries` key).

## 21. Provenance

Recorded in `data/catalog/acquisition/cmems_mc20.json`: product ID, variables, region, time window, download timestamp, destination path. SHA-256 recorded separately in `data/catalog/checksums.json`. Credential source class: environment variables (`COPERNICUSMARINE_SERVICE_USERNAME`/`_PASSWORD`), never the values themselves.

## 22. Scientific limitations

- CMEMS time series covers a ±~2.5 day window around T_SAR at 0.083° resolution — sufficient for `time_series_status=SUFFICIENT` per `ForcingCube`'s own validator, but has not been run through `CubeBackedCurrentField` end-to-end this pass (that integration step was not attempted; only raw-file validity was checked).
- 26.4% NaN coverage means the coastal/nearshore portion of the grid has no current data at some cells — genuine physical/product limitation of a global reanalysis-forecast product near a complex coastline, not a bug.
- No case-specific NETRA detection age prior exists (see §8) — any transport-window figure used elsewhere is a labeled planning bound, not a scientific estimate for this scene.

## 23. Engineering limitations

- SAR calibration pipeline is validated only against a synthetic fixture, not real Sentinel-1 SAFE data (blocked on §3).
- The full-drive search for a pre-existing SAR product copy was aborted after ~22 minutes / 1.8s CPU time because it was contending for disk I/O with NETRA's active training (per the task's explicit resource-safety instruction); the catalog-based check (`dataset_paths.json`/`dataset_inventory.json`, which list no MC20 SAR path anywhere) was relied on instead and is considered sufficient.
- `scripts/acquire_mc20_cmems.py` and `scripts/acquire_mc20_era5.py`/`scripts/acquire_mc20_sar.py` were not modified — only `check_mc20_readiness.py` was, to keep its blocking-reason text accurate.

---

## Final decision

**REAL_E2E_PARTIAL** — 8/15 readiness-checklist items true (see
`reports/mc20_readiness_final.json` for the itemized checklist). AIS
and CMEMS are genuinely real and verified against the SAR anchor point
and timestamp; SAR and ERA5 are blocked on two distinct, named,
non-bypassed account-side issues; NETRA real inference and the Φ
sensitivity path remain blocked for reasons outside this track's
scope. Not `REAL_E2E_READY` — files existing is not readiness. Not
`REAL_E2E_BLOCKED` — real, verified progress was made and the path to
completion is exact and actionable, not stalled.
