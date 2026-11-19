# CMEMS Acquisition Readiness

**Status:** Blocked on credentials. Not bypassed, not downloaded around.
This document specifies exactly what would be requested once an operator
provisions a Copernicus Marine account — it is not itself an acquisition.

## Credential check

`copernicusmarine` (2.4.1) is installed in the project venv. Checked this
pass via `copernicusmarine.login(check_credentials_valid=True)`:

```
INFO - Checking if credentials are valid.
INFO - No credentials found.
INFO - Please provide credentials as arguments or environment variables,
       or use the 'login' command to create a credentials file.
credentials valid: False
```

No `.env`, environment variable, or local credentials file exists for
this service in this environment (confirmed by the same secret-scan
discipline used throughout this project — no `COPERNICUSMARINE_*`
variable set, no credentials file under the default
`~/.copernicusmarine/` location).

**This is the single blocker for any real CMEMS time-series acquisition.**
Nothing else in the pipeline — the reader (`forcing_readers.py`), the
`ForcingCube` schema, the `CubeBackedCurrentField` boundary — is blocked;
all of those are built and tested against structurally-correct data. Only
the actual download is blocked.

## What would be requested, once credentials exist

**Product:** `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` (the same
analysis-forecast product family as the existing single-timestep
`data/raw/cmems/downloaded/ocean physics  drift force data/
cmems_mod_glo_phy_anfc_0.083deg_PT1H-m_*.nc` file) — chosen for
continuity with what is already on disk rather than switching products.

**Variables:** `uo` (eastward sea water velocity), `vo` (northward sea
water velocity) — the two PRATIVARTAN/PRAVAAH actually consume via
`CubeBackedCurrentField`. Not `zos`/`thetao`/`so` (present in the current
snapshot files but unused by any current VARUNA code path) — requesting
only what is used keeps the download minimal, per this project's
acquisition policy.

**Region requirement:** genuinely case-dependent — see
`docs/datasets/FIRST_REAL_E2E_CASE.md`. If Gulf of Mexico (primary
recommendation) is authorized: a bbox around the anchor scene
`zenodo_p1_00073` and its AIS search radius, e.g. roughly lon
[-96,-88], lat [16,24] (generously padded around the already-established
±2° AIS bbox). If Indian Domain (backup): the already-reconciled ERA5
usable domain, 8-20°N/70-85°E (`docs/datasets/ERA5_DOMAIN_POLICY.md`),
for forcing consistency across wind and current.

**Temporal requirement:** a genuine time series, not a snapshot —
`time_series_status=SUFFICIENT` requires ≥2 timesteps per
`ForcingCube`'s own validator (`packages/varuna_data_eng/schemas/
forcing.py`). A minimum useful window is at least a few days at the
product's native hourly resolution, to give PRATIVARTAN's backward
ensemble and PRAVAAH's forward forecast genuine time-dependent current
data to advect through, rather than the single frozen frame the current
files provide. The exact window should be chosen alongside whichever real
SAR case is finally selected (per the First Real E2E Case document),
not fixed here.

**Estimated size:** the existing single-timestep global snapshot is
~300MB (`cmems_mod_glo_phy_anfc_0.083deg_PT1H-m_1787429247253.nc`,
verified on disk). A regionally-subset (not global), multi-day, 2-variable
(not 5-variable) request would be substantially smaller per timestep than
that snapshot, scaled by however many timesteps the chosen window needs —
plausibly tens to low hundreds of MB total for a several-day regional
window, not the multi-GB range. Not downloaded, so not independently
confirmed against this estimate.

**Intended study use:** driving `CubeBackedCurrentField` for
PRATIVARTAN's backward-ensemble origin reconstruction, and
`CubeBackedPravaahProvider`'s forward drift forecast — both already built
and tested against structurally valid synthetic cubes this project's
prior passes; a real regional time series is the only missing piece to
run either for real.

**Acquisition method, once credentials exist:**
```python
import copernicusmarine
copernicusmarine.subset(
    dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
    variables=["uo", "vo"],
    minimum_longitude=..., maximum_longitude=...,  # region-dependent, TBD
    minimum_latitude=..., maximum_latitude=...,
    start_datetime=..., end_datetime=...,           # TBD, case-dependent
    output_filename="cmems_<region>_<window>.nc",
    output_directory="D:/ROUTER(DATASETS)/_downloads/cmems/",
)
```
Downloaded to a new directory under `_downloads/`, checksummed, then
extracted/copied into a **new** raw location (never overwriting the
existing single-timestep snapshots, which remain as-is per this project's
immutability policy) — e.g.
`data/raw/cmems/downloaded/<region>_<window>_timeseries/`.

## Explicitly not done this pass

- No download attempted (would require bypassing the credential check,
  which is not authorized).
- No region/window finalized (depends on the still-open First Real E2E
  Case decision).
- No fallback/anonymous-access path explored — Copernicus Marine does not
  offer one for `subset()`-style regional/variable-scoped requests; only a
  free registered account provides API access.
