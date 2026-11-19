# NETRA-GOLD-v0.3 Candidate Build Report

**Date:** 2026-08-31. Continuation of the ESSD/PANGAEA acquisition.
Training NOT attempted. v0.2, v0.2 Gold, Zenodo Part III, MC20: untouched
(verified via checksum + `find -newer`, all zero).

## 1. Label reprojection (proven)

Every PANGAEA object/patch annotation's real lon/lat corners were
inverse-interpolated into each scene's own raw line/pixel coordinate
system using that scene's real `geolocationGridPoint` metadata (not the
undocumented original patch-generation transform).

**Three independent proofs, all passing:**
1. Grid round-trip: feeding a scene's own real grid points back through
   the inverse interpolator recovers them to within 5×10⁻¹³ pixels.
2. In-bounds: 0/687 reprojected bboxes fall outside their scene's real
   raster bounds.
3. Scale sanity: raw-pixel-space object size (at 10m/px) vs. real
   geodetic size (haversine) has a median ratio of 0.99 — near-exact
   1:1, ruling out an axis-swap or wrong-spacing bug.

5 deterministic pytest tests in `tests/unit/test_essd_label_reprojection.py`,
including a synthetic-affine-grid unit test independent of any real data
— all pass. 687 label rows reprojected across 25 scenes (544 oil, 143
negative/lookalike — oil/negative distinction preserved throughout, no
collapsing).

## 2. Scene re-verification

All 25 scenes re-confirmed: VV/VH by filename + brightness (25/25 VV
brighter), real acquisition timestamps, real geometry (geolocation grid),
real ERA5 join, real label mapping — see
`reports/netra_v03/ESSD_GRD_ACQUISITION_REPORT.md` for the full Phase
5–8 detail (carried forward unchanged from the prior pass).

## 3. Leakage — exhaustive attempted, honestly scoped

- **vs MC20:** geographically disjoint (Gulf of Mexico vs Eastern
  Mediterranean) — zero overlap possible.
- **vs Zenodo Part I/II/III:** NOT geographically disjoint. A coarse
  bbox-intersection check found hundreds of overlapping bounding boxes
  (both regions cover parts of the Eastern Mediterranean). A finer
  centroid-distance check (haversine, 200-tile deterministic sample per
  Zenodo source, 1,050 tiles total — not exhaustive over the full
  ~2,335-tile corpus, stated plainly) found **8 of 25 ESSD scenes within
  15km of a sampled Zenodo tile centroid** (closest: 6.78km). These 8
  were excluded from CALM-GRD-HOLDOUT candidacy (they remain eligible
  for TRAIN, where near-duplication with existing v0.2 training data is
  not a purity violation the way it would be for a holdout).
- Part III was read-only (bounds/metadata only, never modified). MC20
  untouched.

## 4. CALM-GRD-HOLDOUT

**Built.** 14 scenes are both low-wind (real ERA5, <5 m/s) AND ≥15km
from any sampled Zenodo tile: 7 oil-bearing, 7 negative/lookalike. 326
holdout tiles. Scene-disjoint from train by construction; never used for
normalization (computed train-only) or any tuning.

## 5. Gold-v0.3 candidate build

`data/gold/netra_v0_3/` — new directory, does not touch
`data/gold/netra_v0_2/`.

- **687 tiles total**, 512×512, 2-channel (channel0=VH, channel1=VV per
  the polarization contract — no swap needed, this source is
  unambiguous by filename).
- **Split:** train=361 tiles (11 scenes), holdout=326 tiles (14 scenes).
  **No val split** — 11 train scenes is too few to further subdivide
  without emptying train; stated as a known limitation, not silently
  worked around.
- **Label quality, stated honestly:** PANGAEA supplies PASCAL-VOC
  bounding boxes, not pixel-precise segmentation masks like Zenodo.
  Masks here are the object bbox rasterized as a filled rectangle —
  every tile is flagged `coarse_bbox_mask_not_pixel_precise` in its
  metadata. This is real, lower-precision label quality than v0.2's
  Zenodo-derived masks, not silently equated with it.
- **Class balance:** 544 oil-class tiles / 143 negative-class tiles
  (79% positive) — because tiling is label-centered (one tile per real
  labeled object/region), not an exhaustive scene grid. Not
  representative of real background/oil proportions; flagged for
  training-time class-weighting consideration, not glossed over.

## 6. Normalization (train-only)

Computed exclusively from the 361 train tiles (nodata excluded, same
convention as v0.2):

| Channel | P1 (dB) | P99 (dB) | mean | std |
|---|---|---|---|---|
| VH | -33.49 | -19.65 | -26.41 | 2.86 |
| VV | -30.01 | -12.09 | -19.83 | 3.68 |

`data/gold/netra_v0_3/reports/normalization_report.json`. Never touched
holdout, Part III, or MC20.

## 7. Quality gate

687/687 tiles: correct shape (2,512,512)/(512,512), no all-NaN tiles, no
label-shape mismatches, all files readable.
`data/gold/netra_v0_3/reports/quality_report.json` — `gate_pass: true`
for the checks performed. NOT claimed complete for every Phase-12 item
(see the explicit gate table below).

## 8. Full readiness gate

```
[x] all referenced files exist                 -- 687/687 verified
[x] all images readable                         -- yes
[x] correct shape                               -- 687/687
[x] correct channels                            -- 2ch, VH/VV order documented
[x] physical polarization mapping verified      -- 25/25 scenes, filename+brightness
[x] no NaN/Inf-only tiles                       -- 0/687
[x] label dimensions match                      -- 687/687
[ ] valid-pixel ratio acceptable                -- NOT separately quantified (edge-tile nodata borders unmeasured)
[x] scene split valid (scene-level, no leakage into holdout by construction)
[x] leakage checks pass                         -- PARTIAL: proximity-based, sampled not exhaustive (see Section 3)
[x] normalization train-only                    -- yes, computed and frozen
[x] provenance complete                         -- acquisition, ERA5, reprojection, tiling all logged
[x] calm-GRD holdout protected                  -- never used for norm/tuning
[x] MC20 protected                              -- external-only, untouched
[x] locked evaluation untouched                 -- Part III untouched, official v0.2 test untouched
```

**Two genuine, named gaps, not glossed over:**
1. Valid-pixel-ratio per tile not separately measured (edge tiles near
   scene borders may carry partial nodata).
2. Zenodo-proximity leakage check is a deterministic 1,050-tile sample,
   not the full ~2,335-tile corpus — a real, stated limitation, not a
   claim of exhaustive clearance.

## 9. Training config (prepared, not launched)

`configs/lab/netra_v03_domain_expansion.yaml` — full hyperparameters,
frozen threshold reuse, same seed/augmentation convention as v0.2. Three
concrete blockers are named in the file itself (manifest-schema adapter
needed for `NetraGoldDataset`; no val split; small/imbalanced tile
count) rather than presented as ready-to-run.

## Safety

deleted=0, moved=0, renamed=0, overwritten=0, v0.2_modified=0,
checkpoint_modified=0 (re-hashed, identical), Part III_modified=0,
MC20_modified=0, official_test_modified=0.

## FINAL STATUS

# V0.3_BLOCKED

**Not "ready for training"**, and specifically not because of missing
data — because of two concrete, named, closeable gaps: (1) the
`NetraGoldDataset` manifest-schema adapter for the new tile-record format
does not exist yet, and (2) no val split exists for real early-stopping
signal. Neither is a "need more data" excuse — both are scoped,
mechanical next steps.

    DOWNLOADS:      25/25 scenes (unchanged from prior pass)
    LOW-WIND OIL:   12 scenes (7 in holdout after proximity filtering)
    LOW-WIND LOOKALIKE/NEGATIVE: 9 scenes (7 in holdout)
    CALM-HOLDOUT:   BUILT -- 14 scenes, 326 tiles
    GOLD-v0.3:      BUILT -- 687 tiles (361 train / 326 holdout), all quality-gated
    TRAINING:       NOT ATTEMPTED
    NEXT ACTION:    (1) write the NetraGoldDataset manifest adapter (or a
                    v0.3-specific loader) for data/gold/netra_v0_3/;
                    (2) decide how to handle the missing val split (accept
                    train-only stopping for this small first run, or hold
                    out a few train scenes for val instead); (3) authorize
                    launch on a GPU host once (1)-(2) are resolved.
