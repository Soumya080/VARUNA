# AIS Acquisition Specification

**Status:** AIS data is genuinely absent from this machine. `data/raw/ais/`
contains only `.gitkeep` (confirmed by `data/catalog/dataset_inventory.json`,
`status: "missing"`). This document specifies exactly what to acquire and
how it must arrive — it is not a download performed by this pass, per the
"do not download arbitrary datasets based on approximate filenames" rule.

## Why this exists

`packages/varuna_nyaya` (attribution — priors, likelihoods, posterior,
corridor, calibration) and `packages/varuna_chhaya` (if the architecture
decision in `docs/adr/CHHAYA-ARCHITECTURE-DECISION.md` selects the AIS
trajectory model) both consume `VesselTrack`/`AISPoint` from
`varuna_contracts.schemas`. Neither can be validated against real evidence
until real AIS exists on disk.

## Required fields (per the canonical schema)

`packages/varuna_data_eng/schemas/ais.py::RawAISPoint` and
`varuna_contracts.schemas::AISPoint` require, at minimum:

| Field | Type | Required | Notes |
|---|---|---|---|
| `mmsi` | str | required | Maritime Mobile Service Identity, primary key |
| `timestamp` | datetime (UTC) | required | Must be timezone-aware |
| `lon` | float | required | -180..180 |
| `lat` | float | required | -90..90 |
| `sog_knots` | float | optional | Speed over ground |
| `cog_deg` | float | optional | Course over ground |
| `heading_deg` | float | optional | True heading |
| `vessel_type` | enum (`VesselType`) | required at track level | TANKER/CARGO/FISHING/... |
| `imo`, `vessel_name`, `length_m`, `width_m`, `draught_m`, `nav_status`, `destination` | optional | static/voyage data, when available |

## Candidate sources, in priority order

1. **MarineCadastre.gov (NOAA)** — US territorial waters AIS, public domain,
   no license restriction, distributed as monthly CSV/zip. **This is the
   only source that can be acquired automatically without ambiguity** —
   URL pattern is stable (`https://coast.noaa.gov/htdata/CMSP/AISDataHandler/<year>/`),
   format is documented, license is CC0-equivalent (public domain, US
   government work).
2. **Copernicus Marine / EMODnet AIS** — European waters, requires an
   account and has usage restrictions; not auto-downloadable without
   credentials the operator must provide.
3. **National AIS aggregators (e.g. India VTMS / DG Shipping)** for the
   Arabian Sea / Bay of Bengal domain this project's ERA5 forcing actually
   covers — **no public bulk-download endpoint identified**; would require
   a data-sharing agreement. Flagged, not pursued automatically.

### Recommended first acquisition: MarineCadastre, 30-day window

```
dataset: ais_marinecadastre_sample
source: NOAA MarineCadastre.gov AIS Data Handler
official_url: https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/index.html
version: monthly CSV releases, by year/month
expected_format: CSV (zipped), one file per UTM zone per day
expected_size: ~500MB-2GB per month per zone (varies)
checksum: not published by source; compute sha256 on download
license: public domain (US government work, 17 U.S.C. § 105)
reason_required: only publicly-downloadable AIS source identified with a
  stable URL pattern and unambiguous license; needed to validate the
  AISCleaner/raw_to_locked pipeline against real gap/duplicate/speed-anomaly
  patterns before any attribution claim is made against real evidence.
```

**This spec does not download it.** A download would land under
`D:\ROUTER(DATASETS)\_downloads\ais_marinecadastre_sample\`, per Objective 6,
never over an existing extraction, with checksum + provenance recorded
before extraction into a new immutable source directory. It is not
performed here because (a) it is genuinely optional for the Arabian Sea /
Bay of Bengal domain this project targets — US-waters AIS validates the
*pipeline*, not the *deployment region* — and (b) it should be a deliberate,
sized, operator-approved download, not a side effect of a reconciliation
pass.

## What is already built and ready for real data

- `packages/varuna_data_eng/preprocessing/ais_cleaner.py::AISCleaner` — sort,
  dedup, implausible-speed detection (>50kn SOG, >60kn implied speed), gap
  classification (SHORT/MEDIUM/LONG/VERY_LONG), track segmentation.
- `packages/varuna_data_eng/schemas/ais.py::RawAISTrack`, `raw_to_locked()` —
  canonicalization bridge to the locked `VesselTrack` contract.
- `packages/varuna_source_adapters/mock_ais.py::MockAisAdapter` — deterministic
  synthetic tracks, correctly `is_simulated=True`, useful for pipeline testing
  without real data.

## What still needs real data to validate

- Whether `AISCleaner`'s SOG/gap thresholds are calibrated correctly against
  real noisy AIS (they are currently untested against anything but synthetic
  input).
- `AISPoint.position_std_km` inflation across gaps — implemented nowhere yet;
  needs real gap examples to design against.
- The AIS↔SAR-case temporal/spatial join
  (`packages/varuna_geospatial/ais_join.py`, if built) — needs a real track
  density to validate candidate-count behavior is sane (not zero, not
  thousands).

## Acquisition is NOT a substitute for architecture decisions

If `docs/adr/CHHAYA-ARCHITECTURE-DECISION.md` selects the AIS trajectory
model over xView3, AIS acquisition becomes P0 for CHHAYA training data, not
just for NYAYA validation — see that document for the volume/format
implications of that path.
