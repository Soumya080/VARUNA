# OSSDD ↔ CHHAYA Compatibility Analysis

**Status:** Decision-support document. OSSDD was **not downloaded** this
pass (see `data/catalog/acquisition/ossdd.json` for the full acquisition
record and the reason it was deferred). This document evaluates
compatibility from the dataset's officially published specification, not
from a local copy. No CHHAYA training was performed or is recommended by
this document.

## What was verified, and how

OSSDD's identity was confirmed via its own peer-reviewed publication
(arXiv 2608.01963v1, "OSSDD - a New Open Dataset for Sentinel-1 Ship
Detection"), whose data-availability statement names the exact Hugging
Face repository (`sylviaHoch/OpenSARShip-Ship-Detection-Dataset`) as the
official host. The repository page was then fetched directly and its
file listing confirmed to match. This satisfies "verified official
source," not a filename-only guess or an unverified mirror — per the
project's acquisition policy.

**MEASURED** (from the paper / dataset page, not inferred): 15,197
patches, 55,759 annotated ships, VV+VH 32-bit float TIFF chips, AABB +
RBB + binary mask annotations, Sentinel-1 GRD source product, 72.3GB
total, CC-BY-NC-SA-4.0 license (annotations/code) plus Copernicus Sentinel
Data Terms (imagery).

**MEASURED** for xView3-SAR (via its NeurIPS 2022 Datasets & Benchmarks
paper, arXiv 2206.00897): 991 full-scene Sentinel-1 images (~29,400×24,400
px each), VV+VH plus five ancillary layers (bathymetry, wind speed, wind
direction, wind mass, land/ice cover), 243,018 verified maritime object
annotations across >43.2 million km², built by fusing a Global Fishing
Watch detection model with AIS/VMS records. Total scale reported as
~1,400 gigapixels — an order-of-magnitude larger acquisition than OSSDD's
72.3GB (the previous CHHAYA ADR's "~900GB" estimate was a rough prior
figure; ~1,400 gigapixels of raw pixel data corresponds to a download
plausibly in the same very-large range, though the exact archive byte
size was not independently re-verified this pass).

## Compatibility with CHHAYA

### Channel compatibility

**Compatible.** OSSDD's VV+VH 32-bit float chips match the channel
convention NETRA already uses (`in_channels=2`, `[VV, VH]`) and match
what CHHAYA's orphaned LSTM model config (`ChhayaModelConfig`) does *not*
specify (that config is shaped for AIS trajectory sequences, not imagery
— see the existing ADR). If CHHAYA were rearchitected toward a real SAR
detector (option A in the existing ADR), OSSDD's channel layout requires
no conversion.

### Annotation compatibility

**Compatible, and richer than what CHHAYA's wired path (option C)
currently consumes.** The existing `ChhayaProvider.investigate()`
contract returns `List[DarkVesselDetection]` — a position + confidence +
`is_dark` boolean, no bounding box, no mask. OSSDD's AABB/RBB/mask trio is
strictly more detailed than that output shape requires. Using OSSDD would
mean training a real detector and then *reducing* its output down to
`DarkVesselDetection`'s current shape, not a direct fit.

- **AABB support:** direct — any standard object-detection training loop consumes AABB natively.
- **RBB support:** available but not required by the current `DarkVesselDetection` contract; would only matter if CHHAYA's output were extended to carry vessel orientation.
- **Binary mask support:** available but similarly unused by the current contract, which has no segmentation-mask output field.

### Scene identity / split integrity

**Compatible.** `metadata.csv` (per the dataset page) defines train/val/
test splits with scene-level metadata (water/land coverage class) —
consistent with this project's established split policy (scene-level
splitting before tiling, never mixing a scene's tiles across splits,
mirroring exactly what NETRA's own Gold v0.2 manifest already does).
Verifying this in practice (not just from the published description)
would require downloading `metadata.csv` specifically, which was not done
this pass.

### Metadata quality

**Presumed adequate based on the publication**, not independently
verified against a local copy. The paper explicitly markets floating-point
(not compressed 8-bit) imagery as a design advantage for exactly the kind
of downstream scientific use this project does (real dB-scale backscatter,
not quantized/rescaled imagery) — a meaningfully better starting point
than Zenodo Part I/II, whose dB-scale float32 format OSSDD's format
matches.

### Adapter / normalization / Gold requirements, if CHHAYA were rearchitected toward option A

- A new `varuna_chhaya` dataset module analogous to `varuna_netra/dataset/gold.py` (manifest-driven, no directory glob) would need to be built — none exists today; `ChhayaModelConfig`/`create_chhaya_model()` are oriented at trajectory sequences, not imagery, and are not reusable for this.
- Normalization would need a train-only-computed frozen record, exactly like NETRA's `netra-norm-v0.2-nodata-excluded` — OSSDD's own float format makes this directly analogous work, not a new problem class.
- A detector architecture itself does not exist in this codebase (confirmed by the earlier ADR's inspection of `packages/varuna_chhaya/`) — this is the largest gap, independent of which dataset is chosen.

## OSSDD vs. xView3 — direct comparison

| | OSSDD | xView3-SAR |
|---|---|---|
| Scale | 15,197 patches / 55,759 ships | 991 full scenes / 243,018 instances |
| Size | 72.3GB | ~1,400 gigapixels (order of magnitude larger) |
| Channels | VV, VH (float32) | VV, VH + 5 ancillary layers (bathymetry, wind×2, ice/land) |
| Annotation | AABB, RBB, binary mask | Point + is_fishing + is_vessel + length, built from GFW model + AIS/VMS fusion |
| Task shape | Object detection / instance segmentation | Detection + dark-vessel classification (vessel present but no AIS match) — a closer conceptual match to CHHAYA's actual mission (`RADAR_CONTACT_WITHOUT_AIS`) |
| Task fit to current `DarkVesselDetection` contract | Requires reducing rich detection output down to the current simple shape | Directly matches the "dark vessel" concept CHHAYA's `LatentFinding` enum already encodes |
| Acquisition cost | Confirmed feasible now (verified source, moderate size) | Order-of-magnitude larger; feasibility for this project's current disk/network/GPU budget not evaluated this pass |
| License | CC-BY-NC-SA-4.0 (NonCommercial) — flagged | Not verified this pass |

**Neither replaces the need for a real detector architecture.** Both are
data-acquisition answers to a code gap (no SAR detector exists in
`varuna_chhaya` today) that the existing ADR already identified and
recommended deferring (option C: keep the wired AIS-coverage-gap
heuristic, revisit after NETRA's baseline completes and detector work is
separately resourced).

## Recommendation

**SCIENCE-LEAD DECISION REQUIRED.**

This document does not select one. Three options, matching this task's
required framing:

- **OSSDD only** — smaller, faster to acquire (72.3GB, verified source),
  richer per-ship annotation (AABB+RBB+mask) than the current
  `DarkVesselDetection` contract uses, but a conceptually weaker match to
  CHHAYA's actual "dark vessel" mission (general ship detection, not
  specifically AIS-absence-aware).
- **xView3 only** — conceptually the better fit (dark-fishing detection
  built directly from an AIS-fusion methodology, matching CHHAYA's
  `RADAR_CONTACT_WITHOUT_AIS` framing), but an order of magnitude larger
  acquisition and, per the existing ADR, the option explicitly deferred
  until NETRA's baseline is complete and this is separately resourced.
- **OSSDD + xView3** — OSSDD as a faster, smaller proof-of-concept /
  pretraining step before committing to xView3's full acquisition scale;
  not evaluated for technical soundness (e.g. whether pretraining on ship
  detection meaningfully transfers to dark-fishing classification) this
  pass — flagged as a question for the science lead, not answered here.

**This document's own inclination, stated for the record but not acted
on:** neither changes the existing ADR's recommendation to hold at option
C (the wired AIS-coverage-gap heuristic) until NETRA's baseline is done.
Whichever dataset is eventually chosen, it does not change *when* CHHAYA
rearchitecture work should begin — only *what* it should train on once
authorized.
