# ERA5 Domain Policy

**Status:** Defines the one explicit usable study domain for the ERA5 data
already on disk. No new ERA5 download is proposed — the existing 3 files
are re-examined and reconciled, not replaced, per the instruction to prove
the current data cannot satisfy the intended domain before downloading more.

## Source files (unchanged, read-only)

`data/raw/era5/` holds 3 GRIB1 files, verified via cfgrib
(`packages/varuna_source_adapters/forcing_readers.py::read_era5_grib`,
tests in `tests/unit/test_forcing_readers.py`):

| File | Variables | Time steps | Lat range | Lon range |
|---|---|---|---|---|
| `615722de76cc7ca30da7c21a234a1bda.grib` | u10, v10 | 52,608 (hourly) | 5.0–20.0°N | 70.0–85.0°E |
| `954857477a20838e6b6e56852e0fee98.grib` | u10, v10 | 40,560 (hourly) | 6.0–20.0°N | 70.0–85.0°E |
| `data.grib` | u10, v10 | 52,584 (hourly) | 8.0–20.0°N | 70.0–88.0°E |

All three cover the same broad region (Arabian Sea / western Bay of
Bengal) at hourly resolution across overlapping multi-year windows
(2010–2026), but with **three different bounding boxes** — the audit
finding this policy exists to resolve.

## Chosen domain

**Intersection, not union.** A `ForcingCube`'s `spatial_coverage_status`
must never promise coverage a query file cannot deliver — see
`ForcingCube.assert_usable_for_advection()` and `read_era5_grib()`'s
`reference_bbox` intersection logic
(`packages/varuna_source_adapters/forcing_readers.py`).

```
CHOSEN_DOMAIN = BBox(min_lon=70.0, min_lat=8.0, max_lon=85.0, max_lat=20.0)
```

Derivation: `min_lon = max(70.0, 70.0, 70.0) = 70.0`,
`max_lon = min(85.0, 85.0, 88.0) = 85.0`,
`min_lat = max(5.0, 6.0, 8.0) = 8.0`,
`max_lat = min(20.0, 20.0, 20.0) = 20.0`.

This is the largest region for which **all three files simultaneously
provide u10/v10** — a query anywhere in `CHOSEN_DOMAIN` is guaranteed
answerable regardless of which of the three files ends up serving it.

## Source files → this policy

The three files are given consistent roles rather than being merged into
one array on disk (they remain as three separate `ForcingCube`s — no
derived merged GRIB is created; merging is a query-time reconciliation,
not a file-level one):

| Role | File | Reason |
|---|---|---|
| Primary (widest date range) | `615722de76cc7ca30da7c21a234a1bda.grib` | Longest continuous span (52,608 hourly steps), covers the full `CHOSEN_DOMAIN` at its native 5–20°N/70–85°E extent |
| Secondary | `954857477a20838e6b6e56852e0fee98.grib` | Narrower time range (40,560 steps); same lon extent, tighter lat (6–20°N) |
| Tertiary | `data.grib` | Widest spatial extent (8–20°N/70–88°E) but the tightest lat lower-bound of the three, which is what sets `CHOSEN_DOMAIN`'s southern edge |

## Spatial limitations

- Any query with `lat < 8.0°N` is **outside `CHOSEN_DOMAIN`** even though
  two of the three files (the first two) actually extend down to 5–6°N.
  This is deliberate: a caller must not receive inconsistent answers
  depending on which file happens to serve a given query. A future
  refinement could route queries to whichever file's *own* extent covers
  them (rather than the conservative intersection) — flagged as P2, not
  built here, since it adds routing complexity for a domain edge that is
  not currently blocking any real case.
- Any query with `lon > 85.0°E` is outside `CHOSEN_DOMAIN`, even though
  `data.grib` extends to 88.0°E.
- `read_era5_grib(path, reference_bbox=CHOSEN_DOMAIN)` on any of the three
  files returns `spatial_coverage_status=PARTIAL` for the two narrower
  files (their native extent differs from `CHOSEN_DOMAIN`) and `FULL` only
  when the file's native bbox exactly matches — verified behavior, see
  `test_read_era5_grib_reference_bbox_marks_partial` in
  `tests/unit/test_forcing_readers.py`.

## Temporal limitations

- Time ranges differ per file (40,560 to 52,608 hourly steps); no single
  file covers 100% of the union window. A query must specify which file
  (or accept whichever `Era5Adapter.fetch()` selects — currently the
  first file found, see the "no spatial/temporal index yet" note in
  `era5.py`) rather than assume seamless coverage across all three.
- All three are confirmed **hourly** and hold thousands of steps each —
  none of them individually has the CMEMS single-timestep problem.
  `time_series_status=SUFFICIENT` for each file independently.

## What this does NOT resolve

- **No file merging.** Building one unified multi-year, single-bbox ERA5
  array (e.g. via `xr.concat` across the three files' overlapping time
  windows) is real derived-data work with real disk cost. Not done here —
  flagged as P1 if a production call path needs one seamless ERA5 series
  rather than three separately-queryable files.
- **No download decision here.** This policy is scoped to reconciling
  what is already on disk. A genuine gap (e.g. a real study case needing
  `lat > 20°N` or `lon < 70°E`) would justify a new ERA5 request; none has
  been identified, so none is proposed.
