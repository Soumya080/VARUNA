# NETRA v0.3 Label Policy

**In force for every sample in `data/gold/netra_v0_3/`.**

## 1. Label quality is explicit, never implied

Every tile record carries `label_quality` ∈
`{STRONG_PIXEL, WEAK_BOX, COARSE_REGION, UNKNOWN}`.

**All ESSD/PANGAEA-derived v0.3 samples are `WEAK_BOX`.** The loader
asserts this (`test_label_quality_is_weak_box_not_silently_upgraded`) so
a future change cannot silently promote them.

## 2. Why WEAK_BOX is the ceiling (evidence, not assumption)

The full label chain was traced to its origin:

| Evidence | Finding |
|---|---|
| Per-patch PASCAL-VOC XML | `<segmented>0</segmented>` — the VOC standard's own field **explicitly declaring no segmentation masks exist** |
| PANGAEA data table | supplies `obj_*_lon/lat` corners + `obj_patchloc_*` box pixels only; no polygon fields |
| README.pdf / Metadata.txt | describe boxes; no mask product mentioned |
| Authors' own code (Zenodo 10.5281/ZENODO.17789853) | `calculate_perform.py` evaluates detections by **box-IoU against "manual inspections"** — the boxes *are* the ground truth in the source's own methodology |

**Conclusion:** the bounding box is the terminal label. No polygon, mask,
or finer geometry exists anywhere in the chain. Deriving one would be
fabrication.

## 3. Measured box label noise

Per `reports/phase6_box_label_noise.json` (measured on real calibrated
VV, using out-of-box ocean statistics as the reference — **used only to
quantify noise, never to reshape any mask**):

- Median fraction of in-box pixels meaningfully darker than surrounding
  ocean: **37.7%**
- ⇒ **≈62.3% of box-interior pixels are NOT plausibly oil** (median).
- Box area / tile area: median 0.99%, mean 6.04%.

An axis-aligned box around an elongated, often diagonal slick is mostly
clean ocean. This is the physical reason the box cannot be read as a
pixel mask.

## 4. The resulting supervision policy

| Region | Supervision | Justification |
|---|---|---|
| **Outside** every annotation box, within an annotated scene | **Reliable NEGATIVE** | annotators exhaustively boxed all oil objects per patch; absence of a box is real evidence of absence |
| **Inside** an annotation box | **IGNORE** (`IGNORE_INDEX = 255`) | an oil object is present *somewhere* in here, but the source does not identify *which* pixels — identity is genuinely unknown |
| Negative/lookalike tiles | **Reliable NEGATIVE**, full tile | no oil annotated anywhere in the patch |

Both representations ship: `*_mask.npy` (box interior = 1, the naive
weak-box reading) and `*_ignore.npy` (box interior = 1, to be excluded
from loss). The loader applies the ignore policy **by default**;
`apply_ignore=False` reproduces the naive reading and must be declared
in the experiment record if used.

## 5. What is forbidden, explicitly

Not done, and must not be done later:
- inventing contours or shapes inside a box
- morphological erosion/growth tuned to improve a score
- treating box area as confirmed oil pixels
- relabelling ambiguous regions as negatives
- upgrading `WEAK_BOX` to `STRONG_PIXEL` without new source evidence

## 6. Negative/lookalike semantics

The ESSD no-oil set combines clean water, look-alikes, and other benign
phenomena (K-means cluster index only, no reliable per-row semantic
split). All such samples carry `semantic_class = NEGATIVE_OR_LOOKALIKE`.
They are **not** silently called clean background. If finer semantics
are recovered later, they may be split — with tests and documentation.

## 7. Consequence for training

Under this policy, v0.3 supplies **no confirmed positive pixels**. It
therefore cannot, alone, train positive oil segmentation. It supplies
the new low-wind GRD *domain* with trustworthy negatives — which is
precisely the axis on which v0.2 failed at MC20 (false OOD / inability
to interpret calm, low-SNR-VH sea). Positive pixel supervision must come
from v0.2's STRONG_PIXEL Zenodo masks, read-only.
