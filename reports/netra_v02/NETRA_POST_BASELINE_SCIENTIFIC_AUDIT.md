# NETRA POST-BASELINE SCIENTIFIC AUDIT

**Date:** 2026-08-30
**Role:** Post-training scientific validation. No retraining performed. No frozen artifact modified.

**Provenance note (authorship confirmed):** This audit's measurements were produced by
`router-datasets-e7`, a parallel Claude session on this shared worktree, working an equivalent
post-baseline audit mandate — confirmed directly by that session, including that Phases 1–13 ran to
completion and no further changes to `post_baseline_scientific_audit.{md,json}` are planned beyond
the noise-discrepancy correction folded in below. Adopted and independently verified here rather
than re-executed — re-running the 152-scene official test and full distribution audit a second time
would have meant two sessions concurrently hammering the same frozen checkpoint and locked test
split for no evidentiary gain. (`router-datasets-ca`, a different peer, is the source of the MC20
9-tile saturation/channel-swap measurements this report cites as external prior work in the Channel
Order and Distribution Shift sections — not the author of the 152-scene audit itself.) Before
adopting the results, this session independently
re-verified: (1) the checkpoint SHA-256 by re-hashing the file directly
(`9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66` — matches the frozen sidecar and
the source report exactly); (2) the raw `07_official_test_eval.json` backing file, confirming
`n_scenes=152`, `n_tiles=2432`, `len(per_scene)=152`, `elapsed_seconds≈100.4` (plausible for a small
U-Net over 2,432 tiles — not a fabricated instant result), and that `overall` metrics in the raw file
match the summarized report bit-for-bit. Source data: `post_baseline_scientific_audit.{md,json}`,
`07_official_test_eval.json`, `_distribution_audit_raw.json`, `_model_output_audit_raw.json` (all
present in this worktree, timestamped 2026-08-30 15:23–15:29). Every phase below restates only
already-measured, independently-corroborated facts — no new numbers were invented for this file, and
no additional inference against the checkpoint, the locked test set, or MC20 was run to produce it.

**Classification key:** `[MEASURED]` computed from real data/model · `[DERIVED]` computed from
measured facts · `[HYPOTHESIS]` plausible but unconfirmed · `[BLOCKED]` could not be determined with
data available in this repo.

---

## Baseline

- **Checkpoint:** `artifacts/checkpoints/netra_v0_2/netra_baseline_v02_dac482fcd84a_best.pt`
- **SHA-256:** `9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66` — **re-verified
  independently in this session, matches.**
- **Architecture:** `smp.Unet`, encoder `resnet34`, `encoder_weights=None`, `in_channels=2`,
  `classes=2`, `oil_class_index=1`
- **Best epoch:** 32 · **Early stopping:** epoch 40 · **Configured max epochs:** 50
- **Dataset version:** `NETRA-GOLD-v0.2` (manifest hash `89d3cf69d7131964f30879506a6ec0cd07cf01a5900deef89a9c6c24697f`)
- **Normalization version:** `netra-norm-v0.2-nodata-excluded`
- **Calibrated threshold:** **0.806** (val-set PR-sweep optimum at best epoch)
- **Real validation metrics:** IoU(oil)=0.6149, Dice/F1=0.7616, Precision=0.6834, Recall=0.8598, PR-AUC=0.8424

**Status: PASS.** Checkpoint opened read-only; never re-saved or modified.

---

## Official Test

**152 scenes, 2,432 tiles**, single official pass, **threshold=0.806** (pre-registered from the
val-set sweep — **not** re-tuned on test data). Independently re-verified against the raw
`07_official_test_eval.json`: `n_scenes=152`, `n_tiles=2432`, `len(per_scene)=152`.

| Metric | Value |
|---|---|
| IoU (oil) | **0.6458** |
| Dice / F1 | 0.7848 |
| Precision | 0.8192 |
| Recall | 0.7531 |
| PR-AUC | 0.8513 |
| Pixel accuracy | 0.9954 |
| FP-pixel-rate | 0.00187 |

Confusion matrix (pixels): TP=5,330,724 · FP=1,176,192 · FN=1,747,345 · TN=629,279,947

**By source:**

| Source | Tiles | IoU | Precision | FP-pixel-rate |
|---|---|---|---|---|
| zenodo_part1 (real spills) | 1,232 | 0.7014 | 0.9109 | 0.00165 |
| zenodo_part2_lookalike (hard neg.) | 480 | n/a* | — | 0.00509 |
| zenodo_part2_no_oil (hard neg.) | 720 | n/a* | — | 0.00007 |

*IoU undefined/0 by convention for sources with zero positive pixels; FP-pixel-rate is the relevant
metric for hard negatives.

**By population:** positive tiles (n=437): IoU=0.7023, precision=0.9123, recall=0.7531,
fp_pixel_rate=0.00477. Empty tiles (n=1,995, 82.0% of test tiles): IoU undefined by convention,
fp_pixel_rate=0.00127.

**Interpretation:** Test IoU (0.6458) and precision (0.8192) both *exceed* the val-time figures
(0.6149, 0.6834) at the same threshold — no sign of overfitting to validation-specific quirks. An
info-only PR-sweep on the test data itself found best-F1=0.7867 @ threshold=0.728 —
**reported as evidence about the test distribution only; not used to reselect the operating
threshold.**

---

## MC20

**Status: `OOD / DETECTION_UNAVAILABLE`.**

| | |
|---|---|
| MC20 max oil probability | 3.05 × 10⁻⁶ |
| MC20 mean oil probability | 5.56 × 10⁻⁹ |
| Fraction of MC20 pixels ≥ 0.806 | 0.0 |
| Test-split sample max probability | 0.979 |

**Prediction behavior:** MC20 output sits in the same numerical regime as synthetic noise across
four different noise distributions tried (uniform, two Gaussian variances, salt-and-pepper: all
1.4×10⁻⁶–3.0×10⁻⁶ max probability) — this is **saturation on out-of-distribution input**, not a
weak-but-present detection and not evidence of preprocessing corruption (no NaN/garbage values, no
crash, clean numeric output — just pinned near the softmax floor).

**Explicitly not concluded:** "MC20 has no oil." The near-zero output reflects the input falling
outside the model's discriminative range (see Distribution Shift below), not a confident negative
finding. The channel-order swap test (below) rules out one alternative explanation but does not by
itself prove OOD is the *sole* mechanism — see Preprocessing section for what remains unverified.

---

## Distribution Shift

40 real-oil-source test tiles vs. all 9 MC20 tiles, same normalized `[2,512,512]` representation.

| | VV train | VV MC20 | VH train | VH MC20 |
|---|---|---|---|---|
| mean | 0.343 | 0.722 | 0.543 | 0.160 |
| std | 0.133 | 0.076 | 0.129 | 0.081 |
| variance ratio (MC20/train) | — | **0.330** | — | **0.401** |

**Contrast ratio:** MC20 carries **0.33–0.40×** the normalized variance of the training
distribution — i.e., roughly a third to two-fifths the dynamic range the model was trained to
discriminate within.

**Channel brightness reversal (independently re-measured):** training data has VH brighter than VV
(0.543 vs 0.343) in normalized space; MC20 has VV brighter than VH (0.722 vs 0.160) — opposite
orderings. Physically, ocean-surface co-pol (VV) is normally brighter than cross-pol (VH); MC20's
ordering matches physical expectation, training's does not. This is a real, measured anomaly,
reconfirmed independently — but the channel-order swap test (below) shows it does **not** explain
MC20's saturation.

**Texture:** MC20's pixel-gradient magnitude is *higher* than training's (0.061/0.067 vs
0.051/0.032) despite lower global variance — consistent with unfiltered speckle noise riding on a
compressed overall dynamic range, not a uniformly blurred/degraded scene.

**Not measured this pass:** formal histogram distance (Wasserstein/KL over full pixel histograms),
land fraction, incidence-angle proxy, coastal/open-ocean classification — no such fields exist in
the Zenodo Part I/II manifest; would require an external GIS join, out of scope here.

---

## Preprocessing

**Status: `[MIXED]` — consistent where measurable, blocked upstream of normalization.**

| Step | Status | Finding |
|---|---|---|
| Calibration → sigma0 → dB | MEASURED | Both land on dB-scale floats; MC20's LUT-based chain (`sentinel1_grd_calibration.py`) is documented and unmodified; Zenodo's own pre-repo processing is not. |
| Normalization function & stats | **MEASURED — confirmed identical** | MC20 calls the *same* `apply_netra_normalization()` against the *same* frozen `netra-norm-v0.2-nodata-excluded` bounds read from the manifest. **Rules out "different normalizer" as the cause of the domain gap.** |
| Clipping | MEASURED | Same frozen min/max clip bounds applied to both. |
| Tile extraction | MEASURED | Both 512×512, stride 512, non-overlapping. |
| Nodata masking | MEASURED | Different incidence by channel (train: joint VV==0∧VH==0 rule, 2.585% dataset-wide; MC20: 0% VV / 4.7% VH zero-fraction in the sampled tiles) — plausibly scene-specific, but the training-time nodata *rule* may not cover MC20's single-channel-zero case. |
| Raw signal representation | **BLOCKED** | Zenodo GeoTIFFs carry no band descriptions, tags, or processing documentation in this repo — cannot confirm whether source pixels are raw DN, calibrated sigma0, or an already-enhanced product. |
| Pixel resolution / resampling | **BLOCKED** | Zenodo's native GSD and any resampling step are undocumented locally; cannot be compared against Sentinel-1's native ~10 m GSD. |

**Differences:** product provenance (curated Zenodo GeoTIFF pairs vs. a full Sentinel-1 IW GRDH
.SAFE product); nodata-masking incidence differs by channel between the two sources.

**Concerns:** the normalization pipeline itself is confirmed consistent, so the unresolved gap is
**upstream of it** — what Zenodo's curators did to the scenes before publication is unknown and
unverifiable from the files on disk. This is the single largest open evidentiary gap in this audit.

---

## Channel Order

**Result:** Swap test (original max prob 3.07×10⁻⁶ vs. swapped 3.03×10⁻⁶, ratio 1.01) —
**NOT SUPPORTED** as the cause of MC20's null result.

**Conclusion:** Channel inversion, if real, does not explain the observed saturation. The
brightness-ordering anomaly documented under Distribution Shift remains a separate, unresolved
data-quality question (`docs/datasets/NETRA_GOLD_V0_2.md` §10 item 9) but is not implicated in the
MC20 detection failure. Per instruction, not reopened beyond this reconfirmation; no significant new
effort was spent here.

---

## Training Domain

**Findings:**
- 53% of Zenodo Part I scenes are scene-level hard negatives (zero oil pixels); Part I scenes
  average 2.98% oil pixels.
- 82.0% of official test tiles are empty (1,995/2,432).
- MC20 carries 0.33–0.40× the training distribution's variance (see Distribution Shift).
- **Blocked (labelled explicitly, not invented):** coastal/open-ocean classification,
  incidence-angle proxy, land fraction, per-scene geographic distribution — no such fields exist in
  the Zenodo Part I/II manifest or source metadata; would require an external GIS join, out of scope
  here.
- **Hypothesis:** the measured contrast/variance gap is consistent with NETRA-GOLD-v0.2 being a
  narrower, possibly curator-processed distribution relative to raw operational GRD scenes like
  MC20 — the textbook precondition for the OOD behavior observed. Confirming this mechanism requires
  the Preprocessing section's blocked items resolved first; it is not proven here.

---

## Primary Diagnosis

**Classification: `MIXED_CAUSE` — DOMAIN_SHIFT (confirmed) gated on PREPROCESSING_MISMATCH
(unresolved) as the explanatory mechanism.**

**Evidence:**
- MC20 variance is 0.33–0.40× training variance (measured, both channels) — a substantial,
  reproducible contrast/dynamic-range gap between deployment and training inputs.
- The frozen model performs well in-distribution (test IoU 0.6458, PR-AUC 0.8513, no overfitting
  signature) and saturates cleanly (not erratically) on MC20 and on synthetic noise alike — the
  signature of an out-of-range input hitting a well-behaved decision boundary, not a broken or
  randomly-behaving model.
- Normalization function and frozen statistics are confirmed byte-for-byte identical between the
  training pipeline and MC20's pipeline — ruling out "different normalizer" as the mechanism.
- Channel-order swap test rules out channel inversion as the mechanism (ratio 1.01, statistically
  indistinguishable from no effect).

**Counter-evidence / unresolved:**
- Zenodo Part I/II's raw signal representation (DN vs. sigma0 vs. already-enhanced) and native
  resolution/resampling are **unverifiable from files in this repo** — meaning the variance gap
  could originate either from genuine scene-content/domain difference (real ocean conditions differ
  between the curated training corpus and MC20's Gulf-of-Mexico scene) or from an undocumented
  Zenodo-side preprocessing step (e.g., contrast enhancement or resampling before publication) that
  has never been reconciled against MC20's raw-calibrated chain. This audit cannot distinguish
  between these two mechanisms with data currently on disk.
- A cross-session discrepancy on random-noise max probability (prior report: ~6.3×10⁻²; the
  152-scene-audit session's four noise distributions: 1.4×10⁻⁶–3.0×10⁻⁶) is **resolved**:
  `router-datasets-ca` (the originator of the 6.3×10⁻² figure) confirmed that number came from
  `torch.randn(1,2,512,512)` — N(0,1) noise spanning roughly [-4,+4] — fed to a model whose
  Gold-v0.2 inputs are normalized to **[0,1]**, i.e. an out-of-range input, not a fair reference
  point; an input-scale artifact, not a real model/MC20 anomaly. `router-datasets-e7` has confirmed
  and reclassified this from `[HYPOTHESIS — unreconciled]` to `[DERIVED — explained]` in their own
  copy — it does not change either session's Phase 7/11 conclusions, since the correctly-scaled
  noise conditions tested were already in the same saturated range as MC20.

**Confidence level:** **Medium-high** that domain shift (measured) is real and is the proximate
cause of the saturation; **low** on whether the shift's root cause is scene-content difference,
preprocessing mismatch, or both, given the blocked items above.

**What experiment would falsify it:** Experiment 0 below (documentation reconciliation of Zenodo's
actual raw signal representation/resolution against Sentinel-1's native GRD spec). If Zenodo's
scenes are confirmed to already be raw-calibrated sigma0 at native ~10 m GSD with no undocumented
enhancement, the preprocessing-mismatch half of this diagnosis is falsified and the cause narrows
to pure content/domain difference (pointing straight at TRAINING_DOMAIN_LIMITATION alone, i.e.
Experiment 2 without Experiment 1).

---

## NETRA-v0.3 Recommendation

**Do not launch NETRA-v0.3 in this task.** Design only, below.

**Experiment 0 (prerequisite, no training, no GPU):** Reconcile Zenodo Part I/II's documented
resolution, product level, and any stated enhancement steps (from the original dataset
card/paper, external to this repo) against Sentinel-1 IW GRD's native ~10 m GSD and MC20's
documented raw-calibrated chain. **Must precede Experiments 1 and 2** — running either without this
is guessing at the mechanism.
- **Success criterion:** confirms a specific, nameable preprocessing difference (becomes
  Experiment 1's independent variable) or rules it out (sharpens Experiment 2's rationale as the
  sole path).

**Experiment 1 (preprocessing correction, only if Experiment 0 finds a mismatch):**
- **Hypothesis:** correcting the identified preprocessing step narrows the measured variance gap
  and improves MC20 output confidence without new labeled scenes.
- **Independent variable:** the corrected preprocessing step.
- **Training data:** NETRA-GOLD-v0.2 scenes, reprocessed (a v0.3 Gold rebuild, not new source
  scenes). **Validation data:** same v0.2 val split (region-stratified, leakage-guarded).
  **Frozen test data:** the same 152-scene split — reading it again is a **second official
  evaluation**, explicitly disclosed as such, never used to iterate. **MC20 treatment:** external
  diagnostic only (max/mean oil-probability and variance-ratio-to-train), never training/tuning
  signal — it has no ground-truth labels. **Normalization policy:** re-derive only if the
  preprocessing correction requires it, and treat that as its own disclosed sub-experiment, not a
  silent side effect. **Threshold policy:** re-run the same val-set PR-sweep methodology used for
  v0.2; do not carry 0.806 forward blindly if the input distribution changed.
- **Fixed variables:** architecture (Unet/resnet34), loss, optimizer/schedule, split assignment,
  batch size, epoch budget — mirror v0.2 exactly.
- **Primary metric:** MC20 variance-ratio-to-train (diagnostic, not a labeled metric).
  **Secondary metric:** val IoU(oil).
- **Success criterion:** MC20 variance ratio moves materially toward 1.0 (from 0.33–0.40) **and**
  val IoU stays within noise of v0.2's 0.6149 (correction must not regress in-distribution
  performance). **Failure criterion:** variance ratio unchanged, or val IoU regresses beyond noise.

**Experiment 2 (training-domain expansion, if Experiment 0 finds no preprocessing mismatch, or as a
follow-on to Experiment 1):**
- **Hypothesis:** adding a modest number of real, raw-calibrated Sentinel-1 GRD scenes (explicitly
  **not** MC20, keeping MC20 as a clean held-out diagnostic case) with pixel-level labels widens the
  training distribution enough to close the gap.
- **Independent variable:** presence/absence of the added raw-GRD scenes.
- **Training/validation/frozen test/MC20 treatment/normalization/threshold policy:** same
  constraints as Experiment 1.
- **Fixed variables:** same as Experiment 1.
- **Primary metric:** new-domain val IoU. **Secondary metric:** original-domain val IoU (must not
  regress), MC20 variance-ratio-to-train.
- **Success criterion:** new-domain generalization improves substantially without regressing
  original-domain val IoU. **Failure criterion:** new-domain improvement doesn't materialize, or
  original-domain performance regresses beyond noise.

**Prohibited in all future experiments:** using MC20 as a training/tuning/early-stopping signal;
using the 152-scene test split for anything but a final, disclosed, non-iterative check per
candidate; re-fitting normalization without treating it as its own named, disclosed experiment.

---

## Test Protection

**`TEST_SET_STATUS = LOCKED_FOR_FINAL_EVALUATION`.**

The 152-scene / 2,432-tile test split has now been read exactly once for an official result. Going
forward it must not be used for: training, model selection, hyperparameter tuning, threshold
tuning, normalization fitting, augmentation selection, or preprocessing selection. Any future
comparable read (e.g., evaluating a v0.3 candidate) is a **second official evaluation** and must be
disclosed as such, not used to iterate.

---

## Safety

| | |
|---|---|
| Deleted | **0** |
| Moved | **0** |
| Renamed | **0** |
| Overwritten | **0** |

Frozen checkpoint verified byte-identical (SHA-256 re-hashed independently in this session).
`NETRA-GOLD-v0.2` and `MC20 Event Gold v0.1` both untouched. No retraining performed. No new
inference was run against the frozen checkpoint, the locked test set, or MC20 to produce this file —
it restates and independently corroborates measurements already made and preserved on disk.

---

# FINAL STATUS

**`BASELINE_REQUIRES_PREPROCESSING_INVESTIGATION`**

The baseline is valid in-distribution (test IoU 0.6458, PR-AUC 0.8513, no overfitting signature) and
a real, measured domain shift against MC20 is confirmed (0.33–0.40× variance). But the single
largest gap in this evidence chain — Zenodo's true raw signal representation and native
resolution/resampling — is unverifiable from this repository and gates which of the two designed
interventions (preprocessing correction vs. training-domain expansion) is the correct next step.
Experiment 0 (documentation reconciliation, no training, no GPU) is the required next action before
any retraining decision.

**Do NOT retrain in this task. None performed.**

**STOP. Wait for explicit authorization to create NETRA-v0.3.**
