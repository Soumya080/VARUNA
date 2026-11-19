# NETRA v0.3 — Second-Source Acquisition Requirements

**Not an immediate download instruction.** This specifies what a second
source must provide, and exactly why the current one is insufficient.

## Why ESSD/PANGAEA alone is insufficient — with numbers

| Gap | Measured evidence |
|---|---|
| **No pixel-level positives** | source XML declares `<segmented>0</segmented>`; authors evaluate by box-IoU; ~62.3% of box-interior pixels measured not plausibly oil ⇒ 0 confirmed oil pixels available |
| **No geographic diversity** | 25/25 scenes in one Eastern-Mediterranean box (27–36°E, 29–36.4°N) |
| **No temporal diversity** | 25/25 scenes from 2019 only |
| **Small scene count** | 8 train scenes after exhaustive leakage filtering |
| **Contaminated val** | 3/3 val scenes within 15 km of Zenodo tiles |
| **Merged negative semantics** | look-alike vs clean water not separable per row |

The current source *does* successfully deliver the one thing it was
acquired for — verified low-wind regime coverage with real labels
(217 low-wind holdout tiles, 8 clean scenes). It is a genuine domain
sample; it is not a segmentation training corpus.

## Requirements for a second source (ranked)

**Mandatory:**
1. Sentinel-1 **GRD, IW, dual-pol VV+VH**, with per-file-verifiable
   polarization identity (not filename-guessed).
2. **Real pixel-level oil masks** (`STRONG_PIXEL`) — the single most
   important gap. Boxes do not close it.
3. Real acquisition **timestamps** (enables an ERA5 wind join and hence
   regime stratification).
4. Confirmed **low-wind / low-SNR-VH** examples, ideally with positives.
5. Explicit **look-alikes** and **clean negatives** as separable classes.
6. Provenance: product IDs, license, documented annotation protocol.

**Strongly preferred:**
7. Geographic diversity outside the Eastern Mediterranean.
8. Seasonal spread beyond a single year.
9. Acquisition-geometry diversity (orbit, incidence angle).
10. Scene-level separability from Zenodo Part I/II/III footprints
    (verified, not assumed).

**Explicitly not wanted:**
- Ship-detection corpora (OSSDD, xView3) — wrong label type, already
  ruled out.
- Any source overlapping Zenodo Part III's footprints (locked
  evaluation).
- Re-rendered 8-bit patches; raw or calibrated products only.

## Minimum useful size

Small is fine if labels are strong: ~30–60 scene-disjoint scenes with
real masks, ≥10 in low-wind conditions, would materially change the
supervision picture — far more valuable than another 1,000 weak-box
patches.

## Sequencing recommendation

Run the weak-label pilot on the current corpus **first**. Its result
determines whether a second source is needed for domain coverage
(if the pilot shows the domain shift is the bottleneck) or for label
strength (if the pilot is limited by the absence of positive pixels —
the more likely outcome, and predictable from the label analysis above).
