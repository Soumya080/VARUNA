# MC20 Real E2E Acquisition Report

**Case:** MC20 / Taylor Energy, Gulf of Mexico (28.936°N, 88.970°W) — locked
as primary per `docs/datasets/FIRST_REAL_E2E_CASE_FINAL.md`. This document
does not revisit that decision; it closes the data side of it.

## CURRENT STATUS

**Not ready.** One of four required modalities (AIS) is real and on disk.
The other three (SAR, ERA5, CMEMS) are identified/specified but blocked
on three separate, confirmed, unbypassed credential requirements. All
three acquisition scripts are written, tested against the credential
boundary, and will run to completion the moment credentials exist —
no further engineering work is needed to acquire the data once
authorized.

## ACQUIRED DATA

**AIS** — real, already on disk before this pass (`data/raw/ais/2023-01-15/AIS_2023_01_15.csv`,
re-filtered to MC20 in the prior pass): 304,960 in-bbox records, 535
unique vessels, 530 cleaned tracks. No new acquisition this pass.

Nothing else was newly acquired this pass — SAR/ERA5/CMEMS acquisition
all stopped cleanly at their respective credential boundaries, confirmed
below.

## MISSING DATA

- Sentinel-1 GRD scene `S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE`
  (product UUID `6fc676ba-b961-5bfc-9211-8076f8f1481c`, 1,741,458,044 bytes)
- ERA5 u10/v10, MC20-region (28-31°N, -91 to -87°W), 2023-01-11 to 2023-01-17
- CMEMS uo/vo time series, same region/window, product `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m`

## CREDENTIAL BLOCKERS

Three separate, confirmed, unbypassed blockers — each verified this pass
by an actual attempted operation, not assumed from documentation:

| System | What's needed | How verified | Script that uses it |
|---|---|---|---|
| **Copernicus Data Space Ecosystem** (Sentinel-1 GRD download) | Username + password (free account at dataspace.copernicus.eu) | Direct byte-range GET against the confirmed product UUID → **HTTP 401 Unauthorized** | `scripts/acquire_mc20_sar.py` (env vars `CDSE_USERNAME`, `CDSE_PASSWORD`) |
| **Copernicus Marine Service** (CMEMS) | Username + password (free account at marine.copernicus.eu) | `copernicusmarine.login(check_credentials_valid=True)` → `False`, "No credentials found" | `scripts/acquire_mc20_cmems.py` (env vars `COPERNICUSMARINE_SERVICE_USERNAME`, `COPERNICUSMARINE_SERVICE_PASSWORD`) |
| **Climate Data Store / CDS API** (fresh ERA5 region) | A personal API key (free account at cds.climate.copernicus.eu, key from your profile page) | `cdsapi.Client()` → raises "Missing/incomplete configuration file: `~/.cdsapirc`" | `scripts/acquire_mc20_era5.py` (env vars `CDSAPI_URL`, `CDSAPI_KEY`, or a `~/.cdsapirc` file) |

**These are three separate accounts**, not one. None was assumed —
each was independently tested this pass. None was bypassed, scraped
around, or worked past with an invented credential.

**What I need from you, precisely, for each:**
1. **Copernicus Data Space**: a username and password from a free account at https://dataspace.copernicus.eu/
2. **Copernicus Marine**: a username and password from a free account at https://marine.copernicus.eu/
3. **CDS API**: just the API key string from your profile page at https://cds.climate.copernicus.eu/ (the URL is fixed and public, already in the script)

**How to hand them to me safely:** set them as environment variables in
your own shell before your next message referencing this task — e.g.
(PowerShell):
```powershell
$env:CDSE_USERNAME = "..."
$env:CDSE_PASSWORD = "..."
$env:COPERNICUSMARINE_SERVICE_USERNAME = "..."
$env:COPERNICUSMARINE_SERVICE_PASSWORD = "..."
$env:CDSAPI_URL = "https://cds.climate.copernicus.eu/api"
$env:CDSAPI_KEY = "..."
```
I never print these back, never write them into a committed file, and
the three acquisition scripts read them only from the environment at
run time. If it's easier, you can instead run `copernicusmarine login`
and create `~/.cdsapirc` yourself interactively (both are documented,
standard steps for those tools) — either path works with the scripts as
written.

## STORAGE

~1.06TB free on D: (last confirmed this pass). Expected additions:
1.74GB (SAR) + tens of MB (ERA5, 7-day regional subset) + likely tens of
MB (CMEMS, same window) — trivial against available headroom. No
disk-safety concern.

## SAR PIPELINE STATUS

**Built and tested this pass** (`packages/varuna_data_eng/preprocessing/sentinel1_grd_calibration.py`,
9/9 tests passing against a synthetic calibration fixture — **not yet
validated against the real MC20 SAFE product**, which is not downloaded):

- Real GRD radiometric calibration: DN → sigma-nought (linear) → dB,
  using the actual Sentinel-1 calibration-XML LUT format
  (`<calibrationVector>` line/pixel/sigmaNought), bilinearly interpolated
  to the full image grid.
- Normalization reuses the **exact frozen** NETRA Gold v0.2 bounds
  (`data/manifests/netra_gold_v0_2.json::normalization`, not
  re-derived or approximated): VV clip [-42.475, -13.825] dB, VH clip
  [-33.425, -7.525] dB, nodata forced to 0.0.
- 512×512 tiling, matching Gold v0.2's real tiling convention exactly
  (verified against real `pixel_window` entries in the manifest).
- Output shape `[2, H, W]` (VV, VH) — matching the **actually-trained**
  model's `in_channels=2`, confirmed against the live training log's
  `[MODEL] U-Net resnet34 | in_ch=2`.

**A real discrepancy found and NOT silently used:**
`packages/varuna_netra/preprocessing.py::normalize_sar_tile()` — an
existing, older module — produces a 3-channel output (VV, VH, VV/VH
ratio), which does not match the actually-trained 2-channel model. This
module was not reused for the new calibration pipeline; the mismatch is
flagged here rather than silently inherited.

**Explicitly not implemented** (documented in the new module's docstring,
not silently omitted):
- Thermal noise (NESZ) subtraction — biases low-backscatter (oil-slick)
  pixels upward if skipped; a separate noise-LUT parse, not yet built.
- Terrain correction / precise orbit refinement.
- Speckle filtering.

None of these gaps blocks calibration math correctness (proven against
known synthetic values this pass); they are open items for scientific
fidelity once real data is available to evaluate against.

## ERA5 STATUS

Existing 3 files: confirmed via direct coordinate check to cover
8–20°N/70–85°E (Arabian Sea) — MC20 (28.94°N, −88.97°W) is **outside**
that domain. `scripts/acquire_mc20_era5.py` is written and ready: MC20 +
2° buffer region, 2023-01-11 to 2023-01-17 (the honest planning window,
see Temporal Alignment below). Stopped at the CDS API credential
boundary this pass, confirmed by an actual `cdsapi.Client()` call, not
assumed.

## CMEMS STATUS

Existing local files: confirmed single-timestep (`time=1` each,
re-confirmed prior passes) — not used as a fake time series.
`scripts/acquire_mc20_cmems.py` written, targeting the exact product
`docs/datasets/CMEMS_ACQUISITION_READY.md` already specified
(`cmems_mod_glo_phy_anfc_0.083deg_PT1H-m`, uo/vo only), same region/window
as ERA5. Stopped at the Copernicus Marine credential boundary this pass.

## AIS STATUS

Real, complete, unchanged from the prior pass: 304,960 records, 535
vessels, 530 tracks, 0 invalid rows, sourced from an already-downloaded
national file. No new AIS work this pass.

## EVENT GOLD STATUS

**Not built.** Correctly gated behind the three credential blockers
above — an empty or partially-populated `data/gold/varuna_event_v0_1/`
would misrepresent readiness. The structure (`sar/ais/era5/cmems/
metadata/provenance/diagnostics/` + manifest) from the prior document
remains the design target once all four modalities are real.

## SPATIAL ALIGNMENT

Computed by `scripts/check_mc20_readiness.py` from real data:
```
SAR point:            28.936N, -88.970W
SAR ∩ AIS:             non-empty — 304,960 real AIS points within the SAR
                       scene's ~250km IW swath footprint; 38,244 within
                       +/-3h of the acquisition; closest point 3.26km
                       from the anchor coordinate
SAR ∩ ERA5:            N/A — ERA5 not yet covering this region
SAR ∩ CMEMS:           N/A — CMEMS blocked
SAR ∩ AIS ∩ ERA5 ∩ CMEMS: EMPTY
```

## TEMPORAL ALIGNMENT

```
T_SAR                = 2023-01-15T00:02:06.898Z          (real, catalog-confirmed)
T_AIS window          = 2023-01-15T00:00:00Z – 23:59:59Z (real, on disk)
Closest real AIS      = +16m57s, 3.26km (MMSI 368181750, 2023-01-15T00:19:04Z)
                        — this exact figure is preserved unchanged from
                        the prior document, not recomputed differently
T_ERA5 window          = UNAVAILABLE — not yet acquired
T_CMEMS window         = UNAVAILABLE — credential-blocked
```

**Backward/forward transport window — an honest gap, not invented:**
`PrativartanService.reconstruct_origin()`'s `backward_duration_hours` is
computed from a slick's own `age_prior_mean_hours`/`age_prior_std_hours`
— which requires a real NETRA detection. Direct inspection of
`packages/varuna_netra/inference.py::NetraInferenceService.detect()`
found it **still returns a hardcoded mock detection** (`age_prior_mean_hours=12.0,
age_prior_std_hours=2.0` — literally commented "Create a mock detection"),
despite the class name implying real inference. There is therefore no
case-specific transport-window value for MC20, and none was fabricated.
The acquisition scripts use a **planning bound** instead — 84h backward
(the widest hardcoded precedent anywhere in this codebase, from NYAYA's
own service defaults) + 48h forward — explicitly labeled as a planning
bound in both scripts' docstrings, not presented as a computed
scientific value.

## PROVENANCE

Every real number in this report traces to a specific check performed
this pass or the prior one: the AIS figures to
`data/bronze/ais/mc20_2023-01-15_summary.json` (already-verified,
unchanged); the SAR product identity and size to a direct Copernicus
Data Space OData query; the three credential blockers to three direct,
independent authentication attempts (HTTP 401, `login()` → `False`,
`cdsapi.Client()` exception); the calibration pipeline's correctness to
9 passing tests against known synthetic values; the normalization
bounds to a direct read of `data/manifests/netra_gold_v0_2.json`.

## SCIENTIFIC RISKS

- MC20 is a chronic seep — real oil presence on this specific SAR pass
  is well-precedented in cited literature but not confirmed for this
  exact scene without visual/algorithmic inspection post-download (not
  claimed as confirmed here).
- The transport-window planning bound (84h/48h) is a reasonable
  precedent, not a scientifically fitted value for this specific event —
  flagged, not hidden.
- Thermal-noise-uncorrected calibration biases exactly the low-backscatter
  pixels (open water, and — problematically — oil slicks, which also
  suppress backscatter) that matter most for this task. A known,
  documented limitation of the current pipeline.

## ENGINEERING RISKS

- The calibration pipeline is validated only against a synthetic fixture;
  real-scene validation is pending SAR acquisition.
- No live orchestration exists yet to run
  `calibrate_and_tile()`-equivalent logic against a real, multi-GB SAFE
  product's actual directory structure (this pass built the math/tiling
  functions; wiring them to real SAFE-product file discovery — multiple
  measurement TIFFs and calibration XMLs per polarization — is the next
  engineering step once a real product is on disk to test against).
- Three separate credential systems is real operational friction for
  future acquisitions beyond this one case.

## REAL_E2E_READY

**FALSE.**

Exact blockers (from `reports/mc20_readiness.json`, generated this pass):
1. SAR: Copernicus Data Space credentials required
2. ERA5: CDS API credentials required
3. CMEMS: Copernicus Marine credentials required

(No locked-evaluation contamination — verified structurally, MC20's
input set contains none of `zenodo_part3`/`essd`.)

Independent of the above: the validity gate itself remains structurally
blocking (`PHI_DIAGNOSTICS_UNAVAILABLE`, per ADR-0007, Track 2's
unresolved sensitivity-normalization decision) — even once all three
credential blockers are resolved and Event Gold is built, this is a
separate, non-data blocker outside this track's scope.

## EXACT NEXT ACTION

**Awaiting credentials from you**, per the three-item list above. The
moment any one of `CDSE_USERNAME`/`CDSE_PASSWORD`,
`COPERNICUSMARINE_SERVICE_USERNAME`/`COPERNICUSMARINE_SERVICE_PASSWORD`,
or `CDSAPI_URL`/`CDSAPI_KEY` (or `~/.cdsapirc`) is set, the corresponding
`scripts/acquire_mc20_*.py` script is ready to run as-is — no further
code changes needed for that modality. `scripts/check_mc20_readiness.py`
will automatically report that modality as REAL the moment its output
lands in the expected directory.
