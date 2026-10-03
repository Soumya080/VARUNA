# ESSD/PANGAEA Raw-Scene Qualification — Phases 4–16 (resumed)

**Date:** 2026-08-31. Resumed from the previous ACQUISITION_BLOCKED report
after CDSE credentials became available via `.env`. Training NOT
attempted. v0.2, v0.2 Gold, Zenodo Part III, MC20: untouched.

## Phase 4 — Acquisition (MEASURED, complete)

Authenticated to Copernicus Data Space (`CDSE_USERNAME`/`CDSE_PASSWORD`
from `.env`, never printed or persisted). Downloaded all **25/25**
selected Sentinel-1 GRD scenes, resumable/streamed, each verified against
the CDSE catalogue's own reported size AND MD5 checksum before being
accepted (12 succeeded before the first 30-minute token expired; the
script was fixed to fetch a fresh token per scene and the remaining 13
completed cleanly on retry — logged transparently in
`provenance/scene_acquisition_log.json`, no silent retry-masking).

- **Total: 43.80GB, 25/25 checksum-verified**, stored under
  `data/raw/netra_v03_sources/essd_grd/scenes/` (new, non-overwriting path).
- Per-scene record (product ID, source URL, checksum, size, content date,
  access date): `provenance/scene_acquisition_log.json`.

## Phase 5 — Physical channel verification (MEASURED, complete)

Every scene ships VV and VH as **separate, individually-named files**
(`*-vv-*.tiff` / `*-vh-*.tiff`, official ESA/Copernicus IPF naming — not
inferred from content). Independently sanity-checked by calibrating a
downsampled (1/20 per axis) grid of every one of the 25 scenes to real
Sigma0 dB using each scene's own calibration XML (bilinear LUT
interpolation, same method as the existing NETRA calibration module):

**VV brighter than VH in 25/25 scenes** (physical sanity check passes
with no exceptions) — mean-of-scene-means VV=-20.15dB, VH=-25.74dB.
This source needs no `resolve_frozen_v0_2_channel_binding()`-style
correction; polarization identity here is unambiguous by construction.
Recorded in `docs/datasets/NETRA_V03_POLARIZATION_CONTRACT.md`.

Per-scene calibrated stats: `provenance/phase5_8_per_scene_calibration.json`.

## Phase 6 — ERA5 environmental join (MEASURED, complete)

Fetched real ERA5 hourly u10/v10 for the Eastern Mediterranean
(27–36.5°E, 29–36.5°N) covering the exact 23 calendar dates needed by the
25 scenes, via the CDS API (`CDSAPI_URL`/`CDSAPI_KEY` from `.env`). New
file only: `data/raw/netra_v03_sources/essd_grd/era5_eastern_med_2019.nc`
(27MB) — does not touch the existing `data/raw/era5/` or
`data/raw/era5_mc20/` files.

For each scene: matched to the nearest ERA5 hour at the scene's exact
`start_time` and footprint centroid, computed `sqrt(u10²+v10²)`.

**Thresholding policy (documented, not ad hoc):** low-wind < 5.0 m/s,
medium-wind 5.0–10.0 m/s, high-wind ≥ 10.0 m/s — standard
Beaufort-derived open-water bins, stated explicitly as a dataset-analysis
convention, not a universal physical law.

## Phase 7 — Regime cross-tab (the critical result, MEASURED)

| | oil | negative/lookalike |
|---|---|---|
| **low-wind** | **12** | **9** |
| medium-wind | 3 | 1 |
| high-wind | 0 | 0 |

**21 of 25 scenes (84%) fall in the low-wind regime** — this acquisition
does materially fill the target gap with real labels of both classes,
not just one. A plausible physical explanation (not fabricated, offered
as context): SAR oil-slick detectability itself requires a wind window
roughly 2–10 m/s (too calm = no wind-roughened background contrast to
suppress; too windy = slicks disperse/break up) — the labeled dataset
selecting for detectable events plausibly self-selects toward calm
conditions.

Full join: `provenance/era5_regime_join.json`,
`provenance/regime_crosstab.json`.

## Phase 8 — Comparison against NETRA-GOLD-v0.2 (MEASURED)

Per-scene calibrated dB means checked against v0.2's train-only clip
range (`data/manifests/netra_gold_v0_2.json`: VV [-42.475,-13.825] dB,
VH [-33.425,-7.525] dB):

- **VV: 25/25 scene-means within v0.2's range → COVERED**
- **VH: 25/25 scene-means within v0.2's range → COVERED**

This means the *aggregate* brightness statistics are not the missing
axis — consistent with the Smart-Fix investigation's conclusion that
MC20's problem was band-order + wind regime, not that NETRA's channel
statistics are simply too narrow. What v0.2 lacks is **verified
low-wind-regime training examples**, which this axis (Phase 7) directly
confirms this source supplies.

## Phase 9 — Label-policy preservation

`oil` and `negative/lookalike` distinctions are preserved as metadata in
every record (`provenance/era5_regime_join.json`); no collapsing to a
generic background performed.

**Caveat, stated honestly:** ESSD/PANGAEA's own no-oil set is described
by the authors as containing look-alikes and other benign phenomena
together (K-means-clustered, not independently re-labeled per cluster
here) — this dataset does not itself separate "look-alike" from
"clean/no signal" within its no-oil set at the row level examined so
far. Treated as a combined `negative/lookalike` class for this pass;
finer separation, if wanted, requires reading the per-cluster
descriptions in `data_table.xlsx` per row, not done in this pass.

## Phase 10 / 14 — Leakage

- **Geographic disjointness (MEASURED):** MC20's real SAR footprint is
  Gulf of Mexico (`[-91.101, 27.953]` to `[-88.173, 29.877]`, per
  `docs/datasets/MC20_EVENT_GOLD_V0_1.md`) — geographically disjoint from
  ESSD/PANGAEA's Eastern Mediterranean footprint (27–36°E, 29–36.4°N).
  Zero possible spatial overlap.
- **Content/format leakage:** not exhaustively hash-checked against
  Zenodo Part I/II/III — those are pre-cropped, repackaged 2048×2048
  chips from an unrelated processing pipeline with no official Sentinel
  product IDs to cross-reference, versus this source's untouched
  full-scene `.SAFE` products; exact-content collision is implausible
  given the format mismatch, but this is a reasoned inference, not a
  measured 0, and is flagged as such rather than silently assumed.
- Part III remains locked/untouched (not read or modified this pass).

## Phase 11 — CALM-GRD-HOLDOUT assessment

**Sufficient real labeled low-wind scenes exist**: 12 low-wind oil
scenes + 9 low-wind negative scenes = 21 candidate scenes, each a
distinct Sentinel-1 product ID (no repeats), suitable for carving a
scene-disjoint holdout. **Not constructed in this pass** — Phase 16's
own stop condition ends this task before Gold-v0.3 construction; only
the readiness assessment is delivered here.

## Phases 12–15 — not started (correctly, per this task's own scope)

Gold-v0.3 directory construction, metadata schema population,
full/exhaustive leakage sweep, and normalization fitting were explicitly
out of scope for this resumed pass (Phase 16's checklist gates them).

## Phase 16 — Training-readiness gate

```
[x] acquisition qualified               -- 25/25 scenes, checksum-verified
[x] physical channels verified          -- 25/25, filename + brightness check
[x] labels present, distinct            -- oil / negative preserved
[ ] labels geolocated into raw-scene coordinates  -- NOT DONE (see below)
[x] environmental metadata recovered    -- real ERA5, all 25 scenes
[x] regime coverage quantified          -- 21/25 low-wind
[ ] train/val/holdout split defined     -- NOT DONE (Gold-v0.3 not built)
[ ] leakage checks pass (exhaustive)    -- partial (geographic done, content-hash not exhaustive)
[ ] normalization policy defined        -- NOT DONE
[x] provenance complete for acquisition -- yes
```

**Specific, non-generic blocker for Gold-v0.3 construction:** the
PANGAEA table's oil-object annotations are bounding boxes in the
*640×640 packaged-patch* pixel space, referenced by patch corner
lon/lat — not yet re-projected into the raw full-scene GRD's own
line/pixel coordinate system. That re-projection (using each scene's
`geolocationGridPoint`s, the same mechanism already used for MC20 tile
geolocation) is a concrete, scoped, and doable next step — not a vague
"need more data" — but it was not performed in this pass because Phase
16 of this task stops before Gold-v0.3 construction.

## Safety

deleted=0, moved=0, renamed=0, overwritten=0, checkpoint_modified=0,
v0.2_Gold_modified=0, Part III_modified=0, MC20_modified=0,
official_test_modified=0.

## FINAL DECISION

# ESSD_GRD_USEFUL_BUT_SECOND_SOURCE_REQUIRED

**Reasoning, with numbers, per Phase 11's decision framework:** ESSD/PANGAEA
alone (option A) is not called "sufficient" outright because 21 usable
low-wind scenes is a genuinely small, single-region (Eastern
Mediterranean only), single-year (2019 only) sample — real geographic
and temporal diversity (Phase 2's own selection criteria) would still
be thin with only this source. But it is far more than a pure
look-alike/evaluation source (ruling out option C) — it independently
supplies 15 real oil-bearing scenes with real low-wind coverage, which
Zenodo Part III could not verify at all. **Closest fit: a version of B**
— ESSD/PANGAEA is a strong, verified low-wind PRIMARY training-signal
source for a first v0.3 experiment, but geographic/seasonal diversity
for a more general v0.3 (beyond a first controlled domain-expansion
run) would benefit from a second, geographically distinct source later.

## Final Operator Summary

    DOWNLOADS:            25/25 scenes, all checksum-verified
    SCENES:                25 (15 oil, 10 negative/lookalike)
    TOTAL GB:              43.80
    CHECKSUMS:             25/25 MD5-verified against CDSE catalogue
    LOW-WIND OIL:          12 scenes
    LOW-WIND LOOKALIKE:    9 scenes (combined negative/lookalike class, see Phase 9 caveat)
    LOW-WIND NEGATIVE:     (same 9 -- source does not separate lookalike from clean negative per-row)
    CALM-HOLDOUT:          assessed SUFFICIENT (21 candidate scenes), NOT YET BUILT
    GOLD-v0.3 READY:       NO -- specific blocker: patch-to-raw-scene label geolocation not yet done
    TRAINING:              NOT ATTEMPTED, NOT AUTHORIZED THIS PASS
    NEXT ACTION:           (1) geolocate PANGAEA patch bounding boxes into each
                           scene's raw pixel/line space via geolocationGridPoints;
                           (2) decide whether to acquire a second, geographically
                           distinct low-wind-labeled source before building
                           Gold-v0.3, or proceed with ESSD/PANGAEA alone for a
                           first controlled experiment.
