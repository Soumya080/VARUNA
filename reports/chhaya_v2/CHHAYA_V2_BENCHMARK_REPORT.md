# CHHAYA v2 — Pretrained Vessel Detector Benchmark (Phase 1)

**Date:** 2026-09-02. No model was trained or fine-tuned to produce this report.
**Scope:** research/benchmark only, per the governing task's Phase 1 requirement to
investigate candidate pretrained Sentinel-1 vessel detectors *before* selecting one.

## Candidates investigated

### 1. AllenAI / DIUx-xView xView3 submission (`FasterRCNNMultihead`) — investigated in depth

- **Weights**: [`allenai/sar_vessel_detect`](https://github.com/allenai/sar_vessel_detect)
  publishes a public S3 URL for `model.pth`. Downloaded and verified this session:
  **220,622,737 bytes**, sha256
  `9ced010739c61f3a64c632dd2889fc11fbb0ed68e589185f23c89b8b5ab8cb70`. Apache-2.0 license.
- **Finding — the public weights-only repo has no runnable code.** `allenai/sar_vessel_detect`
  contains only `README.md`, `LICENSE`, `environment.yml`, two data files, and a whitepaper —
  the `xview3` Python package its own README instructs you to run
  (`python -m xview3.infer.inference ...`) is **not present in that repository**.
- **Finding — the matching source exists elsewhere.**
  [`DIUx-xView/xView3_fourth_place`](https://github.com/DIUx-xView/xView3_fourth_place) is the
  same team's submission archived with the full `src/xview3/` package included, in particular
  `src/xview3/models/frcnn_multihead.py`.
- **Architecture CONFIRMED by direct inspection**, not assumed: loaded the downloaded
  `model.pth` state_dict (593 tensors) and cross-checked every key/shape against
  `FasterRCNNMultihead.__init__` in `frcnn_multihead.py`. Exact match:
  - A standard **torchvision `FasterRCNN`** (ResNet50+FPN backbone, torchvision's own module
    naming — `backbone.body.*`, `backbone.fpn.inner_blocks/layer_blocks`, `rpn.head.*`,
    `roi_heads.box_head.fc6/fc7`, `roi_heads.box_predictor` with 4 output classes) for box
    proposals.
  - A **second, bare ResNet50 backbone** feeding a small conv head
    (`pred_layer`: 2048→512→512, then `pred_length`/`pred_confidence`/`pred_fishing`/
    `pred_vessel` 4×4 conv heads) for per-detection attribute prediction (length, fishing
    status, vessel/non-vessel, confidence class) — matches the README's description of a
    two-stage "object detection then attribute prediction" pipeline, bundled into one
    checkpoint.
- **BLOCKING finding**: the training configs (`data/configs/final.txt`, `initial.txt`,
  `xval1b...txt` — all three checked, all agree) specify **`Channels = vh,vv,bathymetry`**.
  `conv1` in the checkpoint is confirmed `Conv2d(3, 64, ...)` — a 3rd input channel is
  structurally required, and it is bathymetry, not a derived SAR quantity. Source
  (`xview3/infer/inference.py`): `'bathymetry': 'bathymetry.tif'` — "We always load bathymetry
  so we can eliminate detections on land," loaded from a **per-scene raster file shipped
  alongside VH/VV** in the xView3 dataset's own scene folders.
- **VARUNA does not currently ingest per-scene bathymetry rasters anywhere** (checked:
  `data/raw/`, `packages/varuna_data_eng/varuna_source_adapters/` — no such adapter exists).
  Feeding this model zeros, a duplicated VH channel, or any other stand-in for the missing
  channel would silently and unverifiably change its behavior. Per this task's own non-goal
  ("do not fabricate detection scores"), this candidate is **NOT wired into the live
  pipeline**. It is documented, structurally verified, and left as a swappable
  `detector_source` (`packages/varuna_chhaya/v2/detectors/xview3_frcnn.py`) that reports
  itself `is_available() -> False` and raises rather than approximates — ready to complete
  once bathymetry ingestion exists as its own (out-of-scope-for-CHHAYA) live-data task.
- Secondary, softer finding: `ImageMean=0.5,0.5,0.5` / `ImageStd=0.1,0.1,0.1` and default
  (unconfigured) RPN anchors were recovered from the training configs, but not independently
  validated against the original team's held-out metrics in this pass (the ~1.4-gigapixel
  xView3 validation imagery was not fetched — outside this task's time/compute budget). Even
  after bathymetry is available, this detector should be benchmarked against known-vessel
  scenes before being trusted, not enabled on architecture-match confidence alone.

### 2. Other candidates named in the task — not pursued past a feasibility check

- **xView3 first-place / second-place solutions**: not independently investigated this pass
  once the AllenAI/4th-place investigation above surfaced the shared, structural blocker
  (bathymetry as a required input) that is a property of the **xView3 dataset convention**
  broadly, not specific to one team's model — the same blocker was judged very likely to
  recur. Time was spent going deep on one credible, license-clear, size-reasonable (220MB)
  candidate rather than shallow on several; per the governing task's own instruction to prefer
  depth over an ensemble.
- **SARfish**: identified via search as a *dataset* (`ConnorLuckettDSTG/SARFish` on Hugging
  Face, extending xView3 to SLC imagery) rather than a distinct pretrained *model* — not a
  separate detector candidate.
- **YOLOv8-based SAR vessel detectors**: surfaced in search results as recent literature, not
  as a single credible, licensed, downloadable checkpoint — not pursued given time budget and
  the higher-confidence AllenAI/4th-place finding already in hand.

### 3. Selected for live integration: classical CA-CFAR (`cfar_ca_v1`)

Not a "pretrained model" in the neural sense — the task's own selection criteria
("simplest model that gives a useful operational result," "accurate enough + easy to run +
low integration complexity + reasonable latency," "do NOT automatically use a huge
ensemble") are satisfied more honestly by a real, classical, training-free detector than by
approximating the blocked neural candidate:

- **Cell-Averaging CFAR** (Constant False Alarm Rate): a well-established SAR ship-detection
  algorithm (used as the candidate-generation pre-filter stage in numerous real SAR ship
  detection systems, including several xView3 competitors' own first stage). Computes a local
  clutter mean/std in an annulus around each pixel (excluding a guard band around the pixel
  itself) and flags pixels statistically far above local background.
- Requires **no training, no pretrained weights, no auxiliary data** (no bathymetry, no land
  mask) — runs directly on calibrated VH amplitude.
- **Integration complexity: low.** Pure numpy/scipy, no GPU required, no new dependency beyond
  what the repo already has.
- **Honesty property**: its output is structurally a "standard deviations above local
  background" statistic — there is no plausible way to mistake it for a calibrated
  probability, which makes the RELATIVE_PLAUSIBILITY-not-calibrated-probability requirement
  trivially satisfiable rather than something to remember to enforce.
- **Known, documented limitation**: `threshold_sigma=6.0` is a literature-typical default for
  approximately-Gaussian clutter, **not tuned or validated against VARUNA's own Sentinel-1
  data** in this pass. It should be treated as a reasonable starting point, not a calibrated
  operational threshold — exactly the same posture NETRA's own frozen threshold discussion
  takes in `docs/research/NETRA_TRAINING_MASTER_REPORT.md`.

## Benchmark table

| | xView3 `FasterRCNNMultihead` | CA-CFAR (selected) |
|---|---|---|
| Input format compatibility | VH+VV+**bathymetry** (blocking) | VH (VV optional, unused by v1) |
| Preprocessing requirement | 800×800 chipping, ImageMean/Std normalization, NMS, TTA | none |
| Geolocation requirement | none beyond scene bbox (same as CFAR) | none beyond scene bbox |
| Inference latency | not measured (not run) | measured: see implementation report |
| GPU/CPU requirement | GPU strongly preferred (ResNet50×2 + FPN) | CPU, trivial |
| Detector outputs | bbox, confidence, is_vessel, is_fishing, length | point + score + length_px + n_pixels |
| False-positive behavior | not measured (not run) | not independently validated against real VARUNA data this pass |
| Maritime relevance | purpose-built for exactly this task | general bright-target detector, not vessel-specific |
| Integration complexity | high (missing input, unverified config) | low |
| Selected for live pipeline | **No — NOT_CONFIGURED** | **Yes** |

## Conclusion

The simplest model that gives a useful, honestly-labeled operational result today is the
classical CA-CFAR detector. The credible pretrained neural candidate was not rejected on
"benchmark numbers looking bad" — it was never run, precisely because doing so would have
required fabricating a required input channel this task explicitly forbids fabricating. This
is recorded as a real, actionable, scoped gap (bathymetry ingestion) rather than a permanent
dead end.
