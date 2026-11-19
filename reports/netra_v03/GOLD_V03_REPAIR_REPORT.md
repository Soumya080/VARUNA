# NETRA-GOLD-v0.3 — Data Repair + Label Recovery Report

**Date:** 2026-08-31. No training performed. v0.2 checkpoint, v0.2 Gold,
Zenodo Part III, MC20, official v0.2 test: all untouched and verified.

---

## Source data

25 original Sentinel-1 IW GRDH 1SDV scenes (PANGAEA.980773 / ESSD
17:6807–6837), 43.80 GB, 25/25 MD5-verified. Eastern Mediterranean,
2019. CC-BY-4.0. Real ERA5 wind joined per scene from a live CDS pull.

## Label mapping

Annotations were mapped **lon/lat → raw SAFE line/pixel** using each
scene's own 210 real `geolocationGridPoint`s, bypassing the undocumented
640×640 patch transform entirely. 687 annotations across 25 scenes,
0 skipped, 0 marked `LABEL_MAPPING_UNCERTAIN`.

**Proven four independent ways:**

| Test | Result |
|---|---|
| Grid round-trip on the scene's own points | max error **5×10⁻¹³ px** |
| In-bounds | **0/687** outside raster bounds |
| Geodetic-vs-pixel scale ratio (10 m/px) | median **0.99** (≈1:1) |
| **Physical alignment on real pixels** | box regions darker than surroundings in **98.2%** of oil tiles, t=−35.9, **p≈0** |

The fourth is the strongest: it confirms end-to-end that boxes land on
genuinely oil-like dark water in the raw scenes, not merely that the
arithmetic is self-consistent. 16 deterministic tests cover this.

## Label quality

**`WEAK_BOX` for every sample.** This was not assumed — the whole chain
was searched (PANGAEA table, per-patch XML, README, Metadata, and the
authors' own Zenodo code repo). The XML carries
**`<segmented>0</segmented>`** — PASCAL-VOC's own field asserting that
no segmentation masks exist — and the authors' `calculate_perform.py`
scores detections by **box-IoU against "manual inspections"**. The box is
the terminal label in the source's own methodology.

## Label recovery

No stronger label was recoverable, so none was invented. Instead the
supervision was **restructured** around what the evidence supports:

**Measured (`phase6_box_label_noise.json`):** median **62.3% of
box-interior pixels are NOT plausibly oil** (they sit at ocean
brightness). Box area is a median 0.99% of tile area. An axis-aligned
box around an elongated diagonal slick is mostly clean water.

⇒ Treating box interiors as positive would inject **majority false-positive**
pixel supervision. Adopted policy (Phase 4 Option C/F):

- **outside boxes → reliable NEGATIVE** (annotators boxed all objects)
- **inside boxes → IGNORE** (an object is there; *which pixels* is unknown)

Both arrays ship (`_mask.npy`, `_ignore.npy`); the loader applies ignore
by default. The darkness statistic was used **only to quantify noise** —
never to reshape, erode, or contour any mask.

## Class distribution — a correction

The previously-reported "79% imbalance" was **tile-level**. Measured
**pixel-level** foreground is **4.78%** — the imbalance runs the other
way. Cause decomposition: box geometry (tiny boxes, median 0.99% of
tile) dominates; label-centered tiling drives the tile-level positive
rate; scene concentration was real (one scene held 82 tiles) and has
been capped.

## Tile construction

Deterministic scene-aware sampler: per-scene cap at the P75 count (36),
evenly-spaced selection (not first-N, not duplication). 687 → 600
sampled, then leakage/duplicate exclusions. No positive-tile duplication
anywhere.

## Wind/regime distribution

train 111 low / 106 medium · val 81 low · **holdout 217 low (100%)**.
The holdout is entirely the deployment regime v0.2 lacks.

## Metadata

Per-tile records carry all Phase-13 fields incl. `sample_id`,
`product_id`, `label_quality`, `label_mapping_confidence`,
`wind_source`/`wind_time_offset`, `channel_mapping_version`,
`noise_convention`, `semantic_class`, `quality_flags`. Unavailable
fields (incidence angle, orbit, wind direction) are the literal string
`UNKNOWN` — never fabricated.

## Leakage — the exhaustive check changed the answer

Checked **all 3,020** Zenodo Part I/II/III tile footprints (full corpora,
resumable bounds-only scan, low memory) — not a sample.

- **15/25** scenes lie within 15 km of a Zenodo tile. The earlier
  1,050-tile *sampled* check had found only 8/25 — it **under-detected**,
  and 6 scenes it had cleared were sitting in the holdout.
- Those 6 scenes (77 tiles) were **reclassified out of the holdout**.
  **Holdout is now 0/8 flagged.**
- Cross-split duplicates: **0**. Internal exact duplicates: 8, excluded
  via manifest (files retained, nothing deleted).
- MC20: geographically disjoint. Part III: read-only throughout.

**Honest residual:** train 6/8 and **val 3/3** scenes are proximity-flagged.
For train this is acceptable (nearness to v0.2 training data is not a
holdout-purity violation). For **val it is a real weakness** — val-based
model selection is biased toward the source domain, so the CALM-GRD-HOLDOUT
is the only trustworthy evaluation surface here.

## Train / val / holdout

Scene-level throughout; no scene spans two splits (test-enforced).

| Split | Tiles | Scenes | OIL | NEG/LOOKALIKE |
|---|---|---|---|---|
| train | 217 | 8 | 179 | 38 |
| val | 81 | 3 | 58 | 23 |
| CALM-GRD-HOLDOUT | 217 | 8 | 187 | 30 |

Phase 10 asked for a choice between (A) small pilot with scene-level
validation and (B) acquire more data first. **Chosen: A**, because the
pilot's outcome is what tells us *which* second source we need —
whether the bottleneck is domain coverage or label strength. Acquiring
first would be guessing.

## Normalization

Recomputed from the **final 8 train scenes only** (217 tiles), after the
split was frozen. Version `netra-norm-v0.3-essd-trainonly`.
VH clip [−33.46, −20.05] dB, VV clip [−30.24, −11.85] dB. Val, holdout,
Part III, and MC20 contributed nothing.

## Loader

New `packages/varuna_netra/dataset/gold_v03.py` — **v0.2's `gold.py` is
untouched**. Manifest-driven (no globbing), deterministic sorted order,
excluded tiles never yielded, `label_quality` validated on construction,
ignore masks applied by default, full metadata passthrough, optional
train-only normalization. **11 loader tests + 5 reprojection tests, all pass.**

## Quality gates

```
[x] source products verified          [x] holdout locked (0/8 flagged)
[x] VV/VH verified (25/25)            [x] leakage checked EXHAUSTIVELY
[x] labels correctly mapped (4 proofs)[x] normalization train-only
[x] label quality explicit (WEAK_BOX) [x] provenance complete
[x] no fabricated mask boundaries     [x] metadata complete
[x] scene-level split (test-enforced) [x] loader passes (16 tests)
[x] no NaN/Inf                        [x] image/mask alignment verified (98.2%)
[x] quality statistics generated
```

## Training formulation

Ranked; **Option B (segmentation + ignore-region loss) selected** —
simplest formulation that uses the supervision honestly, and requires
**no architecture change**.

| Option | Verdict |
|---|---|
| A: weak box as positive | **Rejected** — 62.3% measured false-positive pixels |
| **B: ignore regions** | **Selected** — matches the evidence exactly |
| C: weakly-supervised seg | deferred — more machinery, not needed for a first signal |
| D: multi-task | deferred — changes architecture, breaks the controlled comparison |

Because v0.3 contributes **no confirmed positive pixels**, the pilot must
pair it with v0.2's `STRONG_PIXEL` Zenodo masks (read-only) for positive
supervision, while v0.3 supplies the new low-wind domain's negatives —
which is precisely the axis on which v0.2 failed at MC20.

## Cost accounting (measured)

Downloaded 43.80 GB (ESSD) + 26.86 GB (Part III, prior) + 0.027 GB
(ERA5). Processed 43.78 GB extracted. **Final Gold 1.80 GB**, 687 tiles
(+687 ignore masks), 25 scenes. Disk free after: 953 GB.

## Remaining weaknesses

1. No confirmed positive pixels anywhere in v0.3.
2. Val proximity-contaminated (3/3 scenes).
3. Single region, single year; 8 train scenes.
4. Negative/look-alike semantics merged.
5. Wind direction, incidence angle, orbit remain `UNKNOWN`.

---

# GOLD_V03_READY_FOR_WEAK_LABEL_PILOT

**Measured basis:** 687 annotations mapped with 0 uncertain and physical
alignment confirmed at 98.2% (p≈0); label ceiling proven `WEAK_BOX` from
the source's own `<segmented>0</segmented>` and box-IoU evaluation code;
62.3% box-interior noise measured and handled by ignore regions rather
than fabricated contours; leakage checked exhaustively across all 3,020
Zenodo tiles yielding a **0/8-flagged, 100%-low-wind, 217-tile
CALM-GRD-HOLDOUT**; scene-level splits test-enforced; normalization
train-only; 16/16 tests pass.

It is **not** `READY_FOR_FINAL_TRAINING` — that would require positive
pixel labels this source provably does not contain. It is **not**
`SECOND_SOURCE_REQUIRED` yet either: the pilot is what tells us whether
the next source must fix *domain* or *label strength*, and
`NETRA_V03_SECOND_SOURCE_REQUIREMENTS.md` is written and ready for when
it does.

## Next exact action

1. Write `scripts/netra_v03/07_train_v03_pilot.py` using
   `NetraGoldV03Dataset` + a `CrossEntropyLoss(ignore_index=255)`, pairing
   v0.3 train tiles with v0.2 Gold `STRONG_PIXEL` positives (read-only).
2. Run on a GPU host (this machine has none) with architecture frozen.
3. Evaluate on the CALM-GRD-HOLDOUT — never on MC20 or Part III.

## Safety

deleted=0 · moved=0 · renamed=0 · overwritten=0 · v0.2 modified=0 ·
checkpoint modified=0 · Part III modified=0 · MC20 modified=0 ·
official test modified=0.
