# Dataset Release: NETRA-GOLD-v0.2

**Scientific status: EXPERIMENTAL / UNVALIDATED**
**Supersedes:** [NETRA-GOLD-v0.1](NETRA_GOLD_V0_1.md) (retained on disk as historical evidence)
**Build pipeline:** `scripts/netra_v02/01..05_*.py`
**Manifest:** `data/manifests/netra_gold_v0_2.json`
**Gold root:** `data/gold/netra_v0_2/{train,val,test}/`

A successful build does not constitute scientific validation. Nothing in this
document claims the resulting model detects oil spills well; it documents what
the dataset is and how it was made.

---

## 1. What changed from v0.1, and why

v0.1 was built by a pipeline with three defects that made it unusable as a
training set. Each is corrected here, and each correction is measured rather
than asserted.

| | v0.1 | v0.2 | Effect |
|---|---|---|---|
| **Dedup rule** | bounding-box overlap (documented as "MD5/SHA256 Match") | SHA-256 of image bytes **and** mask bytes | Part I retention **374 → 1,199 scenes (3.2×)** |
| **Normalization** | percentiles over all pixels; `VV.p98 = 0.00 dB` | percentiles over valid pixels only; `VV.p98 = −13.83 dB` | statistic now set by backscatter, not by land/border fill |
| **Split** | `hash_random` by scene_id, leakage guard bypassed | geographic, region-stratified, leakage guard enforced | evaluation now measures geographic generalization |
| **Negatives** | none | 1,366 Part II hard negatives | false-positive rate on lookalikes becomes measurable |
| **Sources** | Part I only | Part I + Part II | 374 → **2,565 scenes** |

---

## 2. Sources

| Source | Zenodo record | Role | Scenes found | Passed QC | In pool |
|---|---|---|---:|---:|---:|
| Zenodo Part I (Oil Spill) | 8346860 | `OIL_POSITIVE` | 1,200 | 1,200 | **1,199** |
| Zenodo Part II — Lookalike | 8253899 | `HARD_NEGATIVE_LOOKALIKE` | 685 | 681 | **681** |
| Zenodo Part II — No_Oil | 8253899 | `HARD_NEGATIVE_NO_OIL` | 685 | 685 | **685** |
| **Total** | | | **2,570** | **2,566** | **2,565** |

All licensed CC-BY-4.0. Raw files were opened read-only; none were modified,
renamed, moved or deleted at any stage.

### 2.1 Technical specification (verified on every scene)

- **Sensor:** Sentinel-1, C-band
- **Image:** GeoTIFF, 2048 × 2048, **2 bands (VV, VH)**, float32, sigma-nought dB
- **CRS:** EPSG:4326 with a real geotransform on every image
- **Mask:** GeoTIFF, 2048 × 2048, uint8, labels ⊆ {0, 1}, no CRS
- **Pairing:** 1:1 image↔mask on all 2,570 scenes

### 2.2 Quarantined scenes (4)

Recorded, not deleted, and excluded from the pool:

| Scene | Reason |
|---|---|
| `zenodo_part2_lookalike__00140` | image is 2048×2148, not 2048×2048 |
| `zenodo_part2_lookalike__00166` | image is 2049×2048 |
| `zenodo_part2_lookalike__00288` | image is 2048×2047 |
| `zenodo_part2_lookalike__00390` | image is 2048×2248 |

Off-grid dimensions would break the fixed 4×4 tiling window. They remain on disk
and in `reports/netra_v02/01_source_audit.jsonl`.

---

## 3. Label mapping and the hard-negative policy

```
class 0 = NOT_OIL
class 1 = OIL
```

**Two classes, not three.** Part II Lookalike and No_Oil scenes carry masks whose
unique value set is exactly `{0}` — verified on all 1,370 scenes, with a single
SHA-256 covering all 685 Lookalike masks. The source provides **no pixel-level
lookalike labels**, so lookalike is modelled as a **hard negative** rather than as
a third segmentation class. The original category is preserved per tile in the
manifest (`source`, `label_semantics`) so false positives can be attributed to
Lookalike versus No_Oil at evaluation time.

**Two channels, not three.** The v0.1 configuration declared `in_channels: 3`
(VV, VH, wind). The wind channel has no source: the ERA5 holdings cover
5–20°N / 70–88°E while the Zenodo scenes lie in the Gulf of Mexico, North Sea,
Mediterranean and Red Sea, and Part I carries no acquisition timestamps to join
on. The channel is **omitted rather than fabricated**.

---

## 4. Deduplication (corrected)

**Policy.** An exact duplicate requires *both* image content and mask content to
be identical:

| Case | Verdict |
|---|---|
| same `image_sha256` **and** same `mask_sha256` | exact duplicate → keep one, exclude the rest |
| same image, different mask | **preserve both** |
| same mask, different image | **preserve both** |
| overlapping bounding boxes only | **not a duplicate** |

**Result over 2,566 QC-passed scenes:**

- **1 exact duplicate group** — `zenodo_part1__00356` / `zenodo_part1__00357`; one excluded.
- **1 same-image/different-mask group** — `zenodo_part1__00007` / `zenodo_part1__01339`; both preserved, since two annotations of one scene are two labelled samples, not a duplicate.
- **1 same-mask/different-image group of 1,366** — the identical all-zero negative masks; all preserved, since that is the expected structure of a negative set, not duplication.

Forensic evidence that the v0.1 figure of 826 was a bug, not a property of the data:
**1,198 of 1,200** Part I bounding boxes are distinct and **1,197 of 1,200** file
sizes are distinct, yet a bare greedy footprint-overlap pass reproduces the v0.1
kept/dropped partition (374 / 826) *exactly*.

---

## 5. Split

**Strategy:** `geographic_region_stratified`, seed 42, applied at **scene level before tiling**.

Grouping proceeds in two steps so that no two scenes imaging the same water can
land on opposite sides of a split:

1. **Footprint-overlap components.** Scenes whose bounding boxes intersect are
   unioned into connected components — **594 components** over 2,565 scenes. A
   component is never split.
2. **Geographic regions.** Each component takes the modal 5° lat/lon bin of its
   members — **61 regions**. Whole regions are then dealt to splits.

### 5.1 Why regions are dealt in stratified windows

The first attempt used the obvious greedy rule — give each region to whichever
split is furthest below quota. Region sizes here are very unequal, so the first
few regions overshot val and test and every remaining region fell into train,
producing **59 train regions and exactly one region each for val and test**. That
would have meant evaluating generalization inside a single 5° box.

Regions are instead sorted by size and dealt in fixed windows of ten with
reserved interior slots for val and test, so both evaluation splits span roughly
a tenth of all regions and inherit train's spread of region sizes. Deterministic,
no RNG. A hard guard fails the build if val or test ends with fewer than four
regions.

### 5.2 Resulting split

| Split | Regions | Scenes | Part I | Lookalike | No_Oil |
|---|---:|---:|---:|---:|---:|
| train | 49 | 2,187 | 1,002 | 608 | 577 |
| val | 6 | 226 | 120 | 43 | 63 |
| test | 6 | 152 | 77 | 30 | 45 |

Scene ratios are 85.3 / 8.8 / 5.9 rather than the nominal 80/10/10. That is the
price of atomic regions and it is not tuned away. Every split contains positives
and both hard-negative categories.

---

## 6. Leakage guard

Enforced, not bypassed. The build aborts before Gold generation on any failure.

| Check | Result |
|---|---|
| Scene identity across splits | **PASS** — 0 shared scene IDs |
| Exact content duplication across splits | **PASS** — 0 shared (image, mask) hash pairs |
| Footprint overlap across splits | **PASS** — 0 overlap-components span a split boundary |
| Temporal separation | **UNAVAILABLE** |

### 6.1 Geographic proximity (measured, reported, not claimed as a pass)

Footprint overlap is eliminated by construction, but centroid proximity below the
50 km policy threshold still occurs at region boundaries:

| Pair | Min centroid distance | Pairs < 50 km |
|---|---:|---|
| train / val | 18.4 km | 245 of 494,262 (0.050%) |
| train / test | 24.0 km | 57 of 332,424 (0.017%) |
| val / test | 23.8 km | 24 of 34,352 (0.070%) |

Each scene is ~0.18° (≈20 km) across, so two scenes sharing no water can sit well
under 50 km apart. These are reported as a known limitation rather than resolved
by merging regions, which would collapse the split.

### 6.2 Temporal status: UNAVAILABLE

Neither Part I nor Part II carries acquisition timestamps. The adapters record
`timestamp_status: "unavailable"` and substitute a placeholder that never reaches
scientific logic. **No temporal leakage test can be performed and none is
claimed.** This is written as `UNAVAILABLE` in the manifest, never as `PASS`.
Consequently this dataset supports no claim about temporal generalization.

---

## 7. Normalization

**Computed on the TRAIN split only (2,187 scenes), then frozen and applied
verbatim to val and test.** Never recomputed per split.

**Valid-pixel rule:** `finite AND NOT (VV == 0.0 AND VH == 0.0)`.
Both-channels-zero is the zero-fill convention this corpus uses for land and
scene border. **2.585%** of pooled train pixels are nodata under this rule
(8,935,820,149 valid of 9,172,942,848).

| Channel | v0.1 p2 | v0.1 p98 | **v0.2 p2** | **v0.2 p50** | **v0.2 p98** | v0.2 mean | v0.2 std |
|---|---:|---:|---:|---:|---:|---:|---:|
| VV | −42.55 | **0.00** | **−42.48** | −32.77 | **−13.83** | −32.10 | 6.14 |
| VH | −27.47 | **0.00** | **−33.42** | −20.27 | **−7.52** | −20.33 | 5.50 |

A p98 of exactly `0.00 dB` is not a backscatter percentile. Because ~2.6% of
pixels are exactly zero, the v0.1 98th percentile landed inside the fill mass —
so the statistic measured land, not sea, and would have flipped discontinuously
to about −26 dB on any small change in corpus composition. Excluding nodata
removes both problems.

**Transform:** `x_norm = (clip(x, p2, p98) − p2) / (p98 − p2)`, then nodata pixels
are forced to `0.0` explicitly. Percentiles come from a 0.05 dB histogram over
[−80, +40] dB, exact to the bin width.

Normalization version: `netra-norm-v0.2-nodata-excluded`.

---

## 8. Tiling and Gold layout

- **Order:** split first, tile second. Tiles never influence split assignment.
- **Tile:** 512 × 512, stride 512 → exactly **16 tiles per 2048² scene**, no overlap.
- **Image tensor:** `float32 [2, 512, 512]`, values in [0, 1].
- **Mask tensor:** `uint8 [512, 512]`, labels ⊆ {0, 1}; the loader casts to int64.

```
data/gold/netra_v0_2/
  train/<scene_id>__r{row}c{col}_img.npy
  train/<scene_id>__r{row}c{col}_mask.npy
  val/...
  test/...
```

Each tile records `tile_id`, `scene_id`, `source`, `label_semantics`, `split`,
`row`, `col`, `pixel_window`, `bbox`, `oil_px` and `valid_frac` in the manifest.

**Empty-oil tiles are retained.** Dataset membership and sampling policy are kept
separate: `oil_px` and `valid_frac` are recorded so a sampler can reweight draws
without the dataset silently losing data. Fully-nodata tiles are likewise kept
and counted rather than dropped.

---

## 9. Manifest and how data is read

`data/manifests/netra_gold_v0_2.json` is the **sole** authority on training
membership. It carries dataset id and version, source records with content
hashes, the git commit, scene counts, per-split scene ID lists, the dedup report,
the split and region assignment, the full leakage block, the frozen normalization
record, the label mapping, and one entry per tile.

`NetraGoldDataset` (`packages/varuna_netra/dataset/gold.py`) iterates manifest
entries only. **A directory glob is never used.** Files present in the Gold tree
but absent from the manifest are therefore invisible to training by construction
— this is what closes the v0.1 defect in which 48 stale raw-dB tiles sat
alongside 5,984 normalized ones under a common `*.npy` glob. A missing manifest
raises `GoldManifestError`; no synthetic substitute is ever produced.

---

## 10. Known limitations

1. **No temporal validation is possible.** No timestamps exist in the source.
2. **Geographic proximity below 50 km occurs** across split boundaries for ~0.05% of scene pairs (§6.1).
3. **Split ratios are 85/9/6, not 80/10/10** — a consequence of atomic regions.
4. **No external test set.** Zenodo Part III and ESSD are not present. This dataset supports no cross-dataset generalization claim; its test split is held out from the same corpus.
5. **Severe class imbalance.** Part I scenes average 2.98% oil pixels, and the 1,366 hard negatives contain none, so the pooled positive rate is low. A Dice + weighted cross-entropy loss is used for this reason.
6. **Lookalike is a scene-level category, not a pixel label.** The model cannot be asked to segment lookalikes, only to avoid firing on them.
7. **Two channels only.** No wind, no ancillary features.
8. **`encoder_weights: null`.** Training runs from scratch; ImageNet initialization needs a writable cache and the C: drive is full.
9. **VV/VH band-order assignment is unverifiable from the source files.** `04_build_gold.py` assigns `channels: ["VV", "VH"]` to raw band index 0 and 1 respectively, per Zenodo's documentation — but the raw GeoTIFFs carry no band descriptions or tags (`rasterio` returns empty `descriptions`/`tags()` for every scene checked), so this cannot be independently confirmed against the file itself. Raised as a possible channel-inversion bug during Track 4 cross-session review (2026-08-30); a controlled swap test on out-of-training-distribution data showed no sensitivity to channel order, so it is not the cause of any downstream anomaly found so far, but the underlying labeling still rests on documentation, not verifiable metadata. Also notable on physical grounds: dataset-wide, VH averages 11.8 dB brighter than VV (-20.33 vs -32.10 dB), the reverse of the usual ocean-SAR co-pol/cross-pol ordering — possibly explained by the corpus's land/coastal scene mix, but not confirmed.

---

## 11. Provenance

| | |
|---|---|
| Raw root | `data/raw/zenodo/extracted/` (unmodified) |
| Build scripts | `scripts/netra_v02/01_source_audit.py` … `05_validate_gold.py` |
| Audit evidence | `reports/netra_v02/01_source_audit.jsonl` (2,570 records with per-scene SHA-256) |
| Dedup / split / leakage | `reports/netra_v02/02_dedup_split.json` |
| Normalization | `reports/netra_v02/03_normalization.json` |
| Gold validation | `reports/netra_v02/05_gold_validation.json` |
| Real smoke gate | `reports/netra_v02/06_smoke_test.json` |
| Superseded | `data/gold/netra/` (v0.1) — retained, unused |

---

**Scientific status: EXPERIMENTAL / UNVALIDATED.**
