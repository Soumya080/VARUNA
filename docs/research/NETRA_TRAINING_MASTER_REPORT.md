# NETRA Training & Research Master Report

**Compiled:** 2026-09-01. Read-only reconstruction from repository
evidence (reports, configs, manifests, checkpoints, tests). No training,
no model modification, no dataset modification performed to produce this
document.

**Purpose:** let a new session understand NETRA's full research history
without the original conversation.

---

## 1. Executive Summary

NETRA is VARUNA GRID's SAR oil-spill segmentation model. The frozen
**v0.2 baseline** (ResNet34 U-Net, 2-channel VV/VH Sigma0 dB input) is a
real, working detector on its own training/test domain (official IoU
0.6458). It was found to behave near-OOD on a real deployment case
(**MC20**, Gulf of Mexico, calm-sea Sentinel-1 GRD). A chain of
diagnostic investigations traced this to (a) a genuine channel-binding
bug in the Zenodo training-data ingestion and (b) a real, unaddressed gap
in low-wind/low-SNR-VH training coverage. A domain-expansion dataset
(**NETRA-GOLD-v0.3-CANDIDATE**, from ESSD/PANGAEA real Sentinel-1 GRD)
was acquired, its weak box labels were rigorously characterized
(`WEAK_BOX`, no pixel-level positives), a Multiple-Instance-Learning
(MIL) weak-supervision formulation was designed and unit-tested, and a
full 30-epoch training run (**B1**) was executed on real hardware. **B1
regressed catastrophically on the primary target evaluation** (the
CALM-GRD-HOLDOUT): recall fell 84.8%, IoU fell 84.1%, relative to v0.2
measured on the identical holdout. B1 is **frozen, not deployed, and not
integrated.** v0.2 remains VARUNA's only real detector.

---

## 2. Current NETRA Status

| Item | Current Status | Evidence | Deployment? |
|---|---|---|---|
| **NETRA v0.2** | CURRENT MVP DETECTOR — real, usable in its source domain, known cross-domain limitation | `artifacts/checkpoints/netra_v0_2/netra_baseline_v02_dac482fcd84a_best.pt`, sha256 `9f38c690…2cd66`; official IoU 0.6458, PR-AUC 0.8513, threshold 0.806 (`reports/netra_v02/07_official_test_eval.json`) | **YES** — the only deployed NETRA model |
| **NETRA v0.3-B1** | FAILED RESEARCH INTERVENTION — FROZEN, NOT DEPLOYED | `artifacts/experiments/netra_v03/pilot_01_run2/last.pt`, sha256 `3b76c589…2dd`; verdict `V03_B1_REGRESSION` (`reports/netra_v03/NETRA_V03_B1_FINAL_EVALUATION.md`) | **NO** |
| **NETRA-GOLD-v0.3-CANDIDATE** | Built, quality-gated, weak-labeled (`WEAK_BOX`), used only for B1 | `data/gold/netra_v0_3/` — 687 tiles (361 train/326 holdout pre-final-split; final split 213 train / 81 val / 217 holdout after leakage repair) | Research-only |
| **CALM-GRD-HOLDOUT** | Primary protected evaluation surface, 215–217 tiles / 8 scenes, 100% low-wind, 0/8 proximity-flagged vs Zenodo | `data/gold/netra_v0_3/` holdout split; leakage report `reports/netra_v03/GOLD_V03_REPAIR_REPORT.md` §3 | Never for training |
| **MC20** | External deployment case, evaluation-only | `data/gold/events/mc20_v0_1/`; the false-OOD symptom is understood (Smart-Fix), never used for tuning | External only |
| **Smart-Fix (channel-binding correction)** | Accepted, additive, opt-in inference correction; not in any production build path | `packages/varuna_data_eng/preprocessing/sentinel1_grd_calibration.py::resolve_frozen_v0_2_channel_binding` | Not auto-applied |
| **Current preprocessing / calibration path** | `calibrate_to_db` unchanged, sole production path; NESZ/denoised path exists but is additive, not default | `sentinel1_grd_calibration.py`; Experiment 0/A reports | Production (v0.2 path only) |
| **Next research state** | Awaiting failure-analysis decision on the B1 MIL formulation before any further training | This document, §17 | N/A |

---

## 3. v0.2 Baseline `[MEASURED]`

- **Architecture:** `smp.Unet`, `encoder_name=resnet34`, `encoder_weights=None`, `in_channels=2`, `classes=2`, `oil_class_index=1`. (`artifacts/checkpoints/netra_v0_2/netra_baseline_v02_dac482fcd84a_best.pt.frozen.json`)
- **Checkpoint:** `netra_baseline_v02_dac482fcd84a_best.pt`, sha256 `9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66` — verified unchanged at every checkpoint throughout this entire research chain, including after B1's evaluation.
- **Normalization:** `netra-norm-v0.2-nodata-excluded`, clip_p2_p98_then_scale_unit, computed from v0.2 train split only. Channel clip bounds (as stored, by *stat name* — see channel-semantics note below): "VV" [-42.475,-13.825] dB, "VH" [-33.425,-7.525] dB. (`data/manifests/netra_gold_v0_2.json`)
- **Preprocessing:** `calibrate_to_db` — DN → sigma0 linear via sigmaNought LUT → dB. No thermal-noise subtraction in the production path (a separate `calibrate_to_db_denoised` exists, additive, not default).
- **Channel semantics `[DERIVED, Smart-Fix]`:** the manifest's channel *named* "VV" is physically **VH** (its mean, −32.1 dB, is the darker of the two — VV must be physically brighter than VH over open water). This is a real, measured band-order inversion in the Zenodo ingestion pipeline (`RealZenodoArrayProvider`), confirmed on 120 real Zenodo scenes across 3 sub-corpora with 100% consistency. Frozen v0.2's *learned* channel convention is therefore: **channel 0 = physical VH, channel 1 = physical VV** — this is the convention carried forward into v0.3 for comparability.
- **Training corpus:** Zenodo Part I (oil-positive) + Part II (lookalike/no-oil hard negatives), `STRONG_PIXEL` masks — real, pixel-precise segmentation ground truth. 34,992 train tiles (512×512, tile stride 512).
- **Official evaluation / metrics `[MEASURED]`** (`reports/netra_v02/07_official_test_eval.json`, checkpoint's own frozen sidecar):
  - IoU (oil) = **0.6458** at frozen threshold; sidecar also records 0.614925 at a slightly different eval pass — both are official-test-derived, treat 0.6458 as the headline figure used throughout this research chain.
  - Dice/F1 ≈ 0.7615–0.7848 depending on the exact eval pass cited
  - Precision 0.6834, Recall 0.8598 (frozen sidecar figures)
  - PR-AUC = **0.8513** (headline) / 0.8424 (sidecar)
  - Frozen decision threshold = **0.806** (from a PR-sweep on val, never MC20)

---

## 4. MC20 Failure `[MEASURED / DERIVED]`

**Chain:** real Sentinel-1 SAR (MC20, Gulf of Mexico, 2023-01-15) →
frozen v0.2 calibration+inference → near-zero oil probability, deep in
the numerical floor of the model's output → no trustworthy detection.

**Measured evidence:**
- Original (uncorrected-binding) MC20 max oil probability: **3.0535×10⁻⁶** (oil_logit ≈ −9.624).
- 43.8% of this MC20 crop's VH pixels have signal power **below the sensor's own real, product-supplied noise floor** — independent of any modeling choice (Experiment 0, criterion-independent finding).
- Real ERA5 wind at T_SAR: **4.63 m/s**, 15th percentile of the surrounding week — genuinely calm conditions, not an artifact of preprocessing.

**Distinguishing measured / derived / hypothesis:**
- `[MEASURED]` the raw probability is near the numerical floor; the VH noise-floor fraction; the ERA5 wind value.
- `[DERIVED]` the channel-binding mismatch (via the 120-scene brightness-reversal proof) materially contributes to the false-OOD reading.
- `[HYPOTHESIS→REJECTED]` that a calibration/NESZ implementation bug was the primary cause — Experiment 0/A falsified this (see §5).

---

## 5. NESZ Experiment `[MEASURED / REJECTED]`

**Hypothesis:** the frozen model's near-zero MC20 response is explained
by a thermal-noise-floor / calibration handling defect.

**Pre-registered criterion (fixed before seeing the result):**
- Criterion i: either channel's denoised/raw variance ratio changes ≥0.15 absolute.
- Criterion ii: frozen model's max oil probability increases ≥1000× relative to baseline 3.05×10⁻⁶.

**Calibration path / NESZ implementation:** `calibrate_to_db_denoised`,
new additive function with `below_noise_policy` parameter
(`"floor"`/`"mask"`), parses real noise LUTs from the SAFE product,
verified byte-for-byte against production MC20 Gold at Phase 9 fidelity
check (`max_abs_diff = 0.0`).

**Fidelity check:** exact match to production output when the correction
is not applied — confirms the addition is non-destructive.

**Result:**
- Criterion i: VV delta = 0.173, VH delta = 3.106 → **MET**
- Criterion ii: ratio = 1.67× (need ≥1000×) → **NOT MET**

**A methodological correction made mid-experiment:** the arbitrary
`1e-6` floor for below-noise pixels dominates naive variance statistics
(raw floor-included VH variance ratio = 226×, an artifact); all
decision-relevant numbers exclude floored pixels.

**Decision:** NESZ correction was **implementation-valid but
insufficient** — it changes measurable statistics (criterion i) but does
not move the frozen model's output anywhere near a decision-relevant
range (criterion ii fails by >2 orders of magnitude). The near-zero MC20
response is not explained by a calibration bug.

---

## 6. Smart-Fix Investigation `[MEASURED, fix ACCEPTED]`

**VV/VH discovery:** deterministic sample of 120 real Zenodo training
scenes (40 each from 3 independently-collected sub-corpora) — band 1
brighter than band 0 in **100%** of scenes. Physically, co-pol (VV) must
exceed cross-pol (VH) over open water/lookalikes. `array_provider.py`'s
assumption (band0=VV, band1=VH) is the reverse of reality:
**band0=VH, band1=VV**, confirmed independently 3 ways.

**Frozen-model coherence control:** the frozen v0.2 checkpoint fires
normally (max prob 0.9999) on real positive Zenodo tiles under the
existing (mislabeled) convention — the model is not broken, it learned a
consistent (if physically inverted) convention.

**Corrected MC20 binding, distribution changes:** applying the
correction moves 7 of 8 marginal MC20 statistics into the
training-corpus `[P1,P99]` reference range.

**Frozen model response to correction:** max probability actually
**decreases** (3.0535×10⁻⁶ → 2.1151×10⁻⁶; oil_logit −9.624 → −11.013) —
explicitly *not* treated as a failure of the fix, per the investigation's
own anti-optimization rule ("do not select a change because probability
goes up").

**Decisive comparison:** the corrected-binding MC20 response is
statistically **indistinguishable from real, held-out, in-distribution
negative (no-oil) test tiles** — converting MC20's status from "looks
broken/OOD" to "looks like a genuine, interpretable, currently
unvalidated negative."

**ERA5 low-wind finding:** confirmed via real CDS-sourced ERA5 (not
inferred) — 4.63 m/s, 15th percentile of the surrounding week.

**Critical distinction preserved throughout:** the Smart-Fix corrects a
**false-OOD symptom** (the channel binding). It does **not** establish
that NETRA v0.2 has genuine positive-detection capability in the
calm/low-wind/low-SNR-VH regime — that capability was never tested on a
labeled positive example in this regime, and remains the actual open
question the v0.3 program exists to answer.

**Final decision:** `SMALL_VALID_FIX_FOUND`. The fix
(`resolve_frozen_v0_2_channel_binding`) is additive, opt-in, not called
by any production build script (test-enforced), passed 10 required
gates.

---

## 7. v0.3 Data Expansion `[MEASURED]`

**Source:** ESSD/PANGAEA (PANGAEA.980773 / Yang & Singha 2025, ESSD
17:6807–6837), Eastern Mediterranean, 2019.

**Acquisition:** 25 original Sentinel-1 IW GRDH 1SDV scenes (not the
packaged JPGs), 43.80 GB, **25/25 checksum-verified** against the
Copernicus Data Space catalogue (size + MD5). 15 oil-bearing, 10
negative/lookalike selected scenes, spanning all 12 months of 2019.

**ERA5 join:** real hourly u10/v10 pulled via the CDS API for the exact
23 dates needed, matched to each scene's exact acquisition timestamp and
footprint centroid. **21/25 scenes (84%) low-wind (<5 m/s)**: 12
low-wind oil, 9 low-wind negative.

**Label structure and reprojection:** PANGAEA supplies PASCAL-VOC
bounding boxes with real lon/lat corners per object. These were
reprojected from lon/lat directly into each scene's raw line/pixel
coordinate system using the scene's own 210 real `geolocationGridPoint`s
— bypassing the undocumented 640×640 patch-generation transform
entirely. Proven 4 independent ways: grid round-trip error 5×10⁻¹³ px;
0/687 reprojected boxes out of raster bounds; geodetic-vs-pixel scale
ratio 0.99 (≈1:1); and the decisive **physical alignment check — box
regions are darker than their surroundings in 98.2% of oil tiles
(t=−35.9, p≈0)**.

**Leakage investigation:** exhaustive footprint check across **all
3,020** Zenodo Part I/II/III tiles (not a sample) — 15/25 ESSD scenes
found within 15 km of a Zenodo tile centroid. The earlier *sampled*
(1,050-tile) check had found only 8/25 and under-detected 6 scenes then
sitting in the holdout; those 6 (77 tiles) were reclassified out.
**Final holdout: 0/8 scenes flagged.** MC20 confirmed geographically
disjoint (Gulf of Mexico vs Eastern Mediterranean). Zenodo Part III
never read for content, only bounds-checked; never modified.

**Holdout construction:** CALM-GRD-HOLDOUT = scenes that are **both**
low-wind (real ERA5) **and** ≥15 km from any Zenodo tile — 8 clean
scenes, 215–217 tiles (count varies slightly across build passes; the
final evaluation used 215 tiles / 8 scenes).

**Normalization:** for the pure v0.3-candidate build,
`netra-norm-v0.3-essd-trainonly` was computed from v0.3 train tiles only.
For the **mixed B1 pilot**, a *different*, deliberately chosen
normalization was used instead (see §9) — v0.3's own train-only stats
were explicitly rejected for the mixed run because they created a
domain-identifiable input-statistics shift versus v0.2 (see §9 Bug 2).

**Dataset limitations, stated plainly:**
- **`WEAK_BOX` labels — no confirmed positive pixels** (see §8).
- Only 8–11 clean/usable train scenes; single region, single year.
- Negative/lookalike semantics combined (source does not separate them
  reliably per row).
- Val split (3 scenes) is **proximity-contaminated** (3/3 flagged) —
  diagnostic only, never for model selection.

---

## 8. Label Recovery `[MEASURED]`

**Why naive box-as-positive was rejected:** the PASCAL-VOC XML for every
patch carries **`<segmented>0</segmented>`** — the standard's own field
explicitly asserting no segmentation mask exists. The source authors'
own evaluation code (`calculate_perform.py`, in the linked DARTIS code
repo, Zenodo 10.5281/ZENODO.17789853) scores detections by **box-IoU
against manual inspections** — boxes are the terminal label in the
source's own methodology, not an approximation of something finer.

**Measured box noise:** median **62.3%** of box-interior pixels are
**not plausibly oil** (darkness relative to surrounding ocean, measured
directly on real calibrated VV). Box area is a median 0.99% of tile
area — an axis-aligned box around an elongated, often diagonal slick is
mostly clean water.

**Label-quality policy adopted:** `label_quality = WEAK_BOX` for every
v0.3 sample, never silently upgraded. Outside-box pixels = reliable
negative (annotators exhaustively boxed all objects per patch);
inside-box pixels = `IGNORE_INDEX` for direct pixelwise supervision (the
existence of oil is asserted, its exact pixels are not).

---

## 9. Weak Supervision / MIL `[MEASURED, formulation VALIDATED mechanically — NOT validated for generalization]`

**Two real bugs found before B1, both fixed:**
1. **NaN-loss tiles:** 6 tiles were ~100% box-covered → all-ignore
   target → `CrossEntropyLoss(ignore_index)` returns NaN → would have
   propagated through `backward()` and destroyed all weights. Excluded
   via manifest, regression-tested.
2. **Silent normalization mismatch:** v0.2 Gold stores tiles
   **pre-normalized** to [0,1] at build time; v0.3 stored **raw dB**.
   Same physical VH dB value mapped to inputs differing by up to
   **0.296** purely by source — a free domain-identification shortcut
   for the model. Fixed by normalizing v0.3 with v0.2's frozen
   train-only transform for the mixed pilot
   (`netra-norm-v0.2-COMPAT-for-v0.3-mixed-pilot`).

**Why the ignore-only formulation was insufficient on its own (Blocker
B2):** measured `P(positive pixel | Zenodo train tile) = 0.01416` vs
`P(positive pixel | ESSD train tile) = 0.00000` (exactly, by
construction). Domain predicted label availability perfectly — a model
could reduce loss by learning *"ESSD-looking input → background,"* the
opposite of the domain-generalization goal, and aligned with MC20's
actual documented under-detection failure.

**MIL pooling comparison (real synthetic-controlled test), why
top-k=10% was chosen:** real box sizes span 144→248,320 px (1,700×).
- hard max: a single pathological pixel scores **0.990, higher than a
  real object (0.900)** — trivially exploitable. Rejected.
- LSE: score grows with box size (5.02→12.47); noise-vs-object gap only
  0.06. Rejected.
- noisy-OR: **saturates to ~1.000 on pure noise** at every size —
  unusable. Rejected.
- **top-k mean (k = max(16, 0.10·|box|)):** one-hot pixel
  indistinguishable from noise (0.095 vs 0.095); real object scores ~5×
  higher; stable across the full size range. **Selected.**

**ESSD oversampling ratio:** 10%, chosen from measured re-sampling
counts — 5% leaves most batches without a weak sample; 20–25% re-shows
the 213 weak tiles from only 8 scenes 41–55× per strong epoch
(memorization risk); 10% gives 18.3×.

**Loss formulation:** `L_total = 1.0·L_strong + 1.0·L_weak_negative +
1.0·L_MIL`, `L_MIL = −log(topk_mean(p_oil inside box))`. Unit weights
justified by measured raw magnitudes being the same order
(0.9385/0.9460/0.2032) — not tuned, not selected via MC20/Part III/holdout.

**Gradient analysis (real data, real model):** weak oil-box samples
produced negative gradient on the oil logit for exactly the top 10% of
in-box pixels (matching `topk_frac`) — genuine positive-learning signal.
Negative/lookalike samples produced correct downward gradient. This
measurably **eliminated Blocker B2** at the mechanism level.

**Overfit controls (real data + a synthetic no-location-given control):**
- Strong tile: loss 0.457 → 0.018 (mechanism sanity).
- Weak box, **no pixel location given to the loss**: MIL loss
  0.0866→0.0000; resulting `p_oil` on the true dark object = **0.9996**,
  elsewhere in-box = 0.749, outside-box = 0.0104 — the constraint
  localized the object without being told where it was, and did not
  paint the whole box positive.

**What was actually proven vs. not claimed:** 32 mechanical/mathematical
tests (`test_v03_mil_loss.py`, `test_v03_weak_supervision_mechanics.py`,
`test_gold_v03_loader.py`) prove the loss implements the intended
existence-only weak-supervision semantics correctly, is not degenerate on
controlled synthetic cases, and was not trivially exploitable in a
single-checkpoint diagnostic during training (§10). **None of this
proves the formulation would generalize** — that question is exactly
what B1's evaluation (§11) answers, and it answers it negatively.

---

## 10. B1 Training `[MEASURED]`

| Field | Value |
|---|---|
| Architecture | `smp.Unet`, resnet34, `encoder_weights=None`, in_channels=2, classes=2 — unchanged from v0.2 |
| Normalization | `netra-norm-v0.2-COMPAT-for-v0.3-mixed-pilot` (v0.2 frozen train-only transform, physics-mapped) |
| Channel order | channel0=VH, channel1=VV — identical convention in both sources |
| Loss | `NetraV03WeakSupervisionLoss`: CE(strong) + CE(weak-negative, ignore_index=255) + `−log(topk_mean)` MIL, weights (1.0,1.0,1.0) |
| MIL pooling | top-k mean, `topk_frac=0.10`, `topk_min=16` |
| Optimizer / LR | AdamW / 1e-4 |
| Batch size | 8 |
| Weak sampling ratio | 10% (deterministic, index-based, no file duplication) |
| Gradient clipping | 5.0 (measured pre-clip norms 9.9–82.8 on mixed batches; guard, not tuned) |
| Epochs | 30, **fixed, early stopping DISABLED** (val proximity-contaminated) |
| Seed | 42 |
| Evaluation policy | primary = CALM-GRD-HOLDOUT; diagnostic-only = val; never MC20/Part III/holdout for tuning |

**Hardware (measured, corrects an earlier wrong "no GPU" claim in this
research chain — that claim tested the system Python, not the venv):**
NVIDIA GeForce RTX 3060, 12.88 GB VRAM (11.79 GB free at launch), CUDA
12.4, cuDNN 9.1, torch 2.6.0+cu124. Measured smoke-test peak VRAM 3.80 GB.

**Runtime:** **59,225.8 s (≈16.45 h)**, 30/30 epochs, git commit
`2c87e4f`. A first launch (`pilot_01`) was killed at ~3% due to a
*logging*-only bug (a 20-step log interval aliased exactly onto the
weak-sampler's period-5 pattern, hiding all MIL activity from the
record); fixed to `log_every_steps=17` (coprime with the period) plus
alias-proof window-mean accumulators, and restarted clean as
`pilot_01_run2` — training mechanics themselves were never wrong, only
the log's visibility into them.

**Final training loss (window average):** **0.015973**, down from
0.9429 at start — a ≈98.3% reduction (smoothed first-10 vs last-10
logged windows: 0.912→0.016).

**Gradient behavior:** benign — no NaN-guard trips across the full run;
gradient clipping engaged on a small minority of batches (~1.2%, per the
final evaluation report); no crash, no divergence.

**Checkpoint:** `artifacts/experiments/netra_v03/pilot_01_run2/last.pt`,
sha256 `3b76c589ac220687c78e5db38be171294657ec6819413fd9af32221f6f8e12dd`,
293,460,420 bytes, `epoch=29` (0-indexed, i.e. the 30th and final epoch).
v0.2 checkpoint hash re-verified unchanged throughout.

**Log location:** `artifacts/experiments/netra_v03/pilot_01_run2/metrics.jsonl`
(8,820 logged rows), `train_stdout.log`, `run_metadata.json`.

**Explicitly noted:** training convergence (smooth loss decrease, no
crash) is **not** scientific success — this distinction is exactly what
§11 addresses.

---

## 11. B1 Evaluation `[MEASURED]`

Evaluator: automated post-training pipeline (`reports/netra_v03/NETRA_V03_B1_FINAL_EVALUATION.md`,
`netra_v03_b1_final_evaluation.json`), run after training completed,
against the CALM-GRD-HOLDOUT (215 tiles / 8 scenes), frozen v0.2
threshold 0.806, **never retuned**.

**Verdict: `V03_B1_REGRESSION`**

| Metric | v0.3-B1 | v0.2 (same holdout) | Relative change |
|---|---|---|---|
| IoU (oil) | 0.0199 | 0.1254 | **−84.1%** |
| Dice/F1 | 0.0390 | 0.2229 | **−82.5%** |
| Precision | 0.8238 | 0.7117 | **+15.7%** |
| Recall | 0.0200 | 0.1321 | **−84.8%** |
| PR-AUC | 0.3775 | 0.3928 | −3.9% |
| Foreground fraction | 0.0012 | 0.0092 | **−86.9%** |

Per-scene B1 IoU ranged 0.0011 (worst) to 0.0897 (best), mean scene IoU
**0.0263** vs v0.2's mean scene IoU 0.1190. False-positive rate improved
(0.000225 vs 0.002812) — but via near-total foreground collapse, not
better discrimination.

**Comparability caveat, stated in the source report and preserved here:**
these numbers are **NOT directly comparable** to v0.2's official-test IoU
of 0.6458 — that figure used `STRONG_PIXEL` Zenodo masks; this holdout
uses `WEAK_BOX` labels whose ~62% non-oil interior caps achievable IoU
well below what pixel-precise masks would allow. The **B1-vs-v0.2
comparison on the identical holdout** is the valid comparison, and it is
unambiguous: precision increased, recall and IoU collapsed.

---

## 12. Failure Analysis

**PROVEN `[MEASURED]`:**
- B1 regressed severely on the target holdout relative to v0.2, on the
  identical evaluation surface, identical threshold.
- The regression is a **recall collapse** (foreground prediction
  dropped ~87%), not a numerical/training failure (loss converged
  smoothly, no NaNs, gradients finite throughout).
- The MIL mechanism itself, tested in isolation on synthetic and
  early-checkpoint real diagnostics, was not degenerate (it localized a
  real object without being told its location, and did not paint whole
  boxes positive at epoch 1/epoch 4 checkpoints — see §9 and the earlier
  in-training diagnostics referenced in `reports/netra_v03/`).

**PLAUSIBLE `[HYPOTHESIS, not proven by repository evidence]`:**
- **Conservative-prediction collapse:** mixing a strict existence-only
  MIL constraint with pixelwise strong supervision across 30 epochs may
  have driven the shared decoder toward a globally more conservative
  operating point, even though early-checkpoint diagnostics looked
  localized rather than degenerate.
- **Weak-supervision interaction with strong supervision:** the 90/10
  strong/weak mixing ratio, or the specific unit loss weights, may have
  let the strong-pixel term's own imbalance (1.42% positive) reinforce
  conservatism once combined with a weak term that never asserts full
  positive regions.
- **MIL/top-k interaction:** `topk_frac=0.10` requires only a small
  fraction of a box to be confidently positive to satisfy the
  constraint — this could allow the network to retreat to a tiny,
  very-high-confidence core over many epochs, which is consistent with
  the measured **precision increase alongside recall collapse**.
- **Domain/representation gap:** the ESSD domain (Eastern Mediterranean,
  2019, only 8 usable train scenes) may simply be too narrow a sample
  for the shared architecture to learn a useful, generalizing
  representation from, regardless of the label formulation.
- **Calibration/score suppression:** the frozen 0.806 threshold, chosen
  for v0.2, may be miscalibrated for B1's different output distribution
  — the PR-AUC drop is much smaller (−3.9%) than the fixed-threshold
  IoU/recall drop, which is at least consistent with (though does not
  prove) a threshold/calibration component to the apparent failure.

**UNKNOWN:**
- The exact causal mechanism. No repository evidence isolates which of
  the plausible factors above (or what combination) is dominant. No
  ablation (e.g. MIL weight sweep, topk_frac sweep, strong/weak ratio
  sweep, threshold re-derivation on B1's own PR curve without touching
  the holdout) has been run.

**Explicitly not claimed:** no single hypothesis above is asserted as
proven. The evaluation report itself lists three candidate explanations
(§6 of `NETRA_V03_B1_FINAL_EVALUATION.md`) without adjudicating between
them — that adjudication has not happened.

---

## 13. What Has Been Proven

- v0.2 is a real, working detector on its own domain (`[MEASURED]`,
  official test).
- v0.2's Zenodo training-data channel binding was physically inverted
  relative to reality, and the frozen model learned that inverted
  convention consistently (`[MEASURED]`, 120-scene proof + control).
- The MC20 near-zero response is **not** explained by a NESZ/calibration
  implementation defect (`[MEASURED/REJECTED]`, pre-registered
  criterion).
- The Smart-Fix channel-binding correction converts MC20's response from
  "looks broken/OOD" to "statistically indistinguishable from a real
  in-distribution negative" (`[MEASURED]`).
- ESSD/PANGAEA supplies **zero** confirmed positive pixels — this is a
  property of the source (its own `<segmented>0</segmented>` field and
  evaluation methodology), not a processing choice (`[MEASURED]`).
- The MIL loss mechanism correctly implements existence-only weak
  supervision under mathematical and controlled-synthetic tests, and did
  not exhibit degenerate whole-box-painting behavior on early real
  checkpoints (`[MEASURED]`).
- B1 training was numerically benign — no crashes, no NaNs, smooth
  convergence (`[MEASURED]`).
- **B1 regresses severely versus v0.2 on the identical, leakage-clean,
  never-touched-for-tuning CALM-GRD-HOLDOUT** (`[MEASURED]`) — this is
  the headline scientific result of the entire v0.3 program to date.

## 14. What Has NOT Been Proven

- **Why** B1 regresses — no isolated ablation has separated the
  candidate causes in §12.
- Whether NETRA v0.2 (uncorrected or with the Smart-Fix binding
  correction) has genuine positive-detection capability in the
  calm/low-wind/low-SNR-VH regime at all — this was never directly
  tested on a real, labeled positive example in that exact regime by
  *any* experiment in this chain, v0.2 or v0.3.
- Whether a different MIL weighting, top-k fraction, sampling ratio, or
  threshold would produce a materially different (better or still worse)
  result — no sweep has been run.
- Whether domain shift alone (architecture/representation gap,
  independent of the weak-supervision formulation) would also cause
  regression under a hypothetical strong-label version of the same ESSD
  data — untested, because no strong labels exist for ESSD.
- Whether v0.3 Gold's small scene count (8 train scenes) is itself
  sufficient for any formulation to generalize, independent of the loss
  chosen.

## 15. Current Bottleneck

The evidence does not support forcing a single answer. Two candidates
are both evidentially live and are **not mutually exclusive**:

1. **Weak-supervision formulation risk** — the MIL/ignore-region design,
   as configured (unit weights, `topk_frac=0.10`, 10% sampling), is
   directly implicated by the precision-up/recall-down signature, which
   is a recognizable weak-supervision failure mode (retreat to a
   minimal confident core). This is the most actionable and cheapest
   bottleneck to investigate next (ablation, not new data).
2. **Domain shift / dataset scale** — only 8 usable ESSD train scenes,
   single region, single year; even a well-tuned weak-supervision
   formulation may not have enough signal to teach a generalizing
   representation of the low-wind/calm regime from this alone.

Score calibration (the threshold) is a **secondary, cheap-to-test**
candidate given the PR-AUC-vs-fixed-threshold-metric divergence, and
should be checked (on B1's own PR curve, never re-tuning against the
holdout's labels for selection) before concluding architecture or
dataset changes are needed.

---

## 16. Protected Assets — Never Modify

- `artifacts/checkpoints/netra_v0_2/netra_baseline_v02_dac482fcd84a_best.pt` (v0.2 checkpoint)
- `data/gold/netra_v0_2/` (v0.2 Gold)
- Official v0.2 test split / `reports/netra_v02/07_official_test_eval.json` and its source data
- `data/gold/events/mc20_v0_1/` (MC20 Gold) and the raw MC20 SAFE source under `data/raw/sentinel1_grd/mc20_2023-01-15/`
- `artifacts/experiments/netra_v03/pilot_01_run2/last.pt` (B1 checkpoint) and its `pilot_01/` predecessor's artifacts
- `data/gold/netra_v0_3/holdout/` and its provenance (`tile_records_v2.json`'s holdout entries) — the CALM-GRD-HOLDOUT
- `data/raw/netra_v03_sources/zenodo_part3/` (Zenodo Part III, locked external evaluation)
- All frozen scientific reports under `reports/netra_v02/` and `reports/netra_v03/`

---

## 17. Future Research Options (NOT to be implemented in this task)

Ranked by cost/information-gain, per the source master prompt's
categories:

**1. No-compute diagnostics** (cheapest, do first)
- *Question:* is B1's regression a calibration/threshold artifact or a
  genuine representational collapse?
- *Evidence supporting it:* PR-AUC dropped only 3.9% while
  fixed-threshold IoU/recall dropped >84% — a large threshold-metric
  divergence.
- *Cost:* near-zero (re-derive a PR curve from already-computed B1
  holdout probabilities; no new inference, no training).
- *Risk:* low; worst case it doesn't explain the gap and rules out one
  hypothesis cheaply.

**2. Cheap ablations** (next cheapest — reruns, not new data)
- *Question:* does the MIL weighting/top-k/sampling-ratio choice cause
  the recall collapse?
- *Evidence supporting it:* precision-up/recall-down is a textbook
  minimal-confident-core weak-supervision signature; §9's design choices
  (unit weights, `topk_frac=0.10`, 10% ratio) were justified by mechanism
  tests, not by any generalization test.
- *Cost:* moderate — each ablation is a full ~16h GPU run unless a
  shorter-budget proxy run is designed first.
- *Risk:* moderate; could still not isolate the cause if domain shift
  dominates.

**3. Stronger-label acquisition**
- *Question:* does the ceiling come from ESSD's `WEAK_BOX` labels
  specifically?
- *Evidence supporting it:* §8's measured 62.3% box-interior noise; the
  MIL formulation cannot supply true pixel-level positive gradient.
- *Cost:* high (a new dataset acquisition, per
  `docs/datasets/NETRA_V03_SECOND_SOURCE_REQUIREMENTS.md`, already
  written).
- *Risk:* high effort for uncertain payoff if the bottleneck is actually
  domain diversity (§15, option 2) rather than label strength.

**4. Context-aware modeling** (e.g. explicit wind/ERA5 input feature)
- *Question:* would exposing the model to the environmental regime
  directly (not just via pixel statistics) help it distinguish genuine
  calm-sea slicks from noise?
- *Evidence supporting it:* the entire v0.3 motivation is a
  wind-regime-specific gap; ERA5 is already integrated into the data
  pipeline.
- *Cost:* moderate (architecture change — a second input head).
- *Risk:* changes architecture, breaking the "domain is the only
  variable" controlled-comparison design used so far; would need its own
  fresh baseline.

**5. Domain adaptation** (explicit feature-alignment methods)
- *Question:* does the domain gap require more than shared-weight
  mixed-batch training to bridge?
- *Evidence supporting it:* B2's original diagnosis (domain predicts
  label availability) suggests the domains may be too separable in
  representation space for naive mixing.
- *Cost:* high (new methodology, new implementation, new validation
  cycle).
- *Risk:* high implementation complexity for a first intervention;
  premature before cheaper diagnostics are exhausted.

**6. Future NETRA retraining** (a clean v0.4 from scratch with revised
   data/labels/formulation)
- *Question:* should NETRA be retrained wholesale rather than
  incrementally patched?
- *Evidence supporting it:* none yet — this is the most expensive option
  and should follow, not precede, the cheaper diagnostics above.
- *Cost:* very high.
- *Risk:* very high without first understanding B1's specific failure
  mode.

---

## 18. Exact Next Decision

Per the governing task's explicit instruction: **do not implement
anything from §17 in this task.** The next decision belongs to whoever
picks up this report, and should be: **run option 1 (no-compute PR-curve
/ threshold diagnostic on the already-computed B1 holdout probabilities)
first**, since it is free, uses data already on disk, and can
immediately narrow §12's hypothesis set before any further GPU time is
spent. Only after that should ablations (option 2) be considered, and
only with an explicit, pre-registered success criterion — following the
same discipline used successfully in Experiment 0 (§5).

---

## Evidence-Rule Compliance

Every substantive claim above is tagged `[MEASURED]`, `[DERIVED]`,
`[HYPOTHESIS]`, `[UNKNOWN]`, or `[REJECTED]` in the section it appears,
per the governing task's evidence rule. No hypothesis in §12 or §15 is
asserted as proven; §13/§14 explicitly separate what repository evidence
actually establishes from what remains open.
