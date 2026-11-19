# NETRA Post-Baseline Scientific Audit

**Date:** 2026-08-30
**Role:** Post-training scientific validation. No retraining performed. No frozen artifact modified.
**Classification key:** `[MEASURED]` computed from real data/model this pass · `[DERIVED]` computed from measured facts · `[HYPOTHESIS]` plausible but unconfirmed · `[BLOCKED]` could not be determined with data available in this repo.

---

## Phase 1 — Checkpoint Integrity `[MEASURED]`

| | |
|---|---|
| Checkpoint | `artifacts/checkpoints/netra_v0_2/netra_baseline_v02_dac482fcd84a_best.pt` |
| SHA-256 | `9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66` |
| Matches frozen sidecar | **Yes** |
| Architecture | `smp.Unet`, encoder `resnet34`, `encoder_weights=None` |
| in_channels / classes / oil_class_index | 2 / 2 / 1 |
| Best epoch | 32 (early-stopped at 40) |
| Dataset version | `NETRA-GOLD-v0.2` |
| Manifest hash | `89d3cf69d7131964f30879506a6ec0cd07cf01a5900deef89a9c6c24697f` |
| Normalization version | `netra-norm-v0.2-nodata-excluded` |
| Calibrated threshold | **0.806** |

**Status: PASS.** Checkpoint opened read-only; never re-saved.

---

## Phase 2 — Official Test Evaluation `[MEASURED]`

152 scenes, 2,432 tiles, single pass, threshold = **0.806** (pre-registered from the val-set sweep — **not** re-tuned here).

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

*IoU is undefined/0 by convention for sources with zero positive pixels; FP-pixel-rate is the relevant metric for hard negatives.

**Interpretation:** Test IoU (0.6458) and precision (0.8192) both *exceed* the val-time figures (0.6149, 0.6834) at the same threshold — no sign of overfitting to validation-specific quirks. Hard-negative false-positive rates remain low.

An info-only PR-sweep on the test data itself found best-F1=0.7867 @ threshold=0.728 — **reported as evidence about the test distribution only; not used to reselect the operating threshold.**

---

## Phase 3 — Test Set Freeze `[DERIVED]`

**`TEST_SET_STATUS = LOCKED_FOR_FINAL_EVALUATION`**

The 152-scene / 2,432-tile test split has now been read exactly once for an official result (Phase 2). Going forward it must not be used for: model selection, hyperparameter tuning, threshold tuning, normalization fitting, augmentation selection, or preprocessing selection. Any future comparable read (e.g. evaluating a v0.3 candidate) is a **second official evaluation** and must be disclosed as such.

---

## Phase 4 — MC20 Domain Diagnostic `[MEASURED]`

| | |
|---|---|
| MC20 max oil probability | 3.05 × 10⁻⁶ |
| MC20 mean oil probability | 5.56 × 10⁻⁹ |
| Fraction of MC20 pixels ≥ 0.806 | 0.0 |
| Test-split sample max probability | 0.979 |

**Status: `OOD / DETECTION_UNAVAILABLE`.** Explicitly **not** concluded: "MC20 has no oil." The near-zero output reflects input falling outside the model's discriminative range (see Phase 6), not a confident negative finding.

---

## Phase 5 — Preprocessing Consistency Audit `[MIXED]`

| Step | Status | Finding |
|---|---|---|
| Calibration → sigma0 → dB | MEASURED | Both land on dB-scale floats; MC20's explicit LUT-based chain is documented, Zenodo's is not. |
| Normalization function & stats | **MEASURED — confirmed identical** | MC20 calls the *same* `apply_netra_normalization()` against the *same* frozen `netra-norm-v0.2-nodata-excluded` bounds read from the manifest. **This rules out "different normalizer" as the cause of the domain gap.** |
| Clipping | MEASURED | Same frozen min/max clip bounds applied to both. |
| Tile extraction | MEASURED | Both use 512×512, stride 512, non-overlapping. |
| Nodata masking | MEASURED | Different incidence by channel (train: joint VV==0∧VH==0 rule, 2.585% dataset-wide; MC20: 0% VV / 4.7% VH zero-fraction in this audit's sample) — plausibly scene-specific, but the training-time nodata *rule* may not cover MC20's single-channel-zero case. |
| Raw signal representation | **BLOCKED** | Zenodo GeoTIFFs carry zero band descriptions/tags/documentation in this repo — cannot confirm whether source pixels are raw DN, calibrated sigma0, or an already-enhanced product. |
| Pixel resolution / resampling | **BLOCKED** | Zenodo's native GSD and any resampling are undocumented locally; cannot be compared against Sentinel-1's native ~10 m GSD. |

**Summary:** the normalization pipeline itself is confirmed consistent. The unresolved gap is **upstream of it** — what Zenodo's curators did to the scenes before publication is unknown and unverifiable from the files on disk.

---

## Phase 6 — Distribution Audit `[MEASURED]`

40 real-oil-source test tiles vs. all 9 MC20 tiles, same normalized `[2,512,512]` representation.

| | VV train | VV MC20 | VH train | VH MC20 |
|---|---|---|---|---|
| mean | 0.343 | 0.722 | 0.543 | 0.160 |
| std | 0.133 | 0.076 | 0.129 | 0.081 |
| variance ratio (MC20/train) | — | **0.330** | — | **0.401** |

- **Channel brightness reversal (new, independently measured this pass):** in normalized space, training data has **VH brighter than VV** (0.543 vs 0.343); MC20 has **VV brighter than VH** (0.722 vs 0.160) — opposite orderings. Physically, ocean-surface co-pol (VV) is normally brighter than cross-pol (VH); MC20's ordering matches this, training's does not. This reconfirms the cross-session channel-order concern independently, though Phase 8's swap test already shows it does **not** explain the saturation.
- **Texture:** MC20's pixel-gradient magnitude is *higher* than training's (0.061/0.067 vs 0.051/0.032) despite lower global variance — consistent with unfiltered speckle noise riding on a compressed overall dynamic range, not a uniformly blurred scene.
- Not measured this pass: formal histogram distance (Wasserstein/KL), land fraction, incidence-angle proxy, coastal/open-ocean classification (all `[BLOCKED]` — no such fields exist in the manifest).

---

## Phase 7 — Model Output Audit `[MEASURED]`

| Input | max prob | mean prob | frac ≥ 0.806 |
|---|---|---|---|
| Train sample (n=20) | 0.99989 | 0.0332 | 0.0225 |
| Val sample (n=20) | 0.99991 | 0.0133 | 0.0109 |
| Test sample (n=20) | 0.97906 | 0.0047 | 0.0018 |
| **MC20 (all 9)** | **3.05e-06** | 5.57e-09 | 0.0 |
| Random noise (4 distributions tried) | 1.4e-06 – 3.0e-06 | ~1e-9 | 0.0 |

**Verdict: MC20 = SATURATED / OOD**, in the same output regime as synthetic noise, not the "weak-but-present" or "preprocessing-invalid" regimes.

**Discrepancy flagged and now reconciled (2026-08-30, confirmed directly by router-datasets-ca):** a prior cross-session measurement reported random-noise max probability as ~6.3×10⁻², about four orders of magnitude above this audit's own measurement (1.4–3.0×10⁻⁶) across four different noise distributions. **Root cause, confirmed by the reporting session itself:** that measurement used `torch.randn(...)` — `N(0,1)`, values spanning roughly [-4,+4] — fed directly to a model expecting `[0,1]`-normalized input, an input-scale bug in that test. Re-measured on the same checkpoint with correctly in-range inputs: `U[0,1]`=1.39e-06, `N(train mean/std)`=8.75e-07, `N(MC20 mean/std)`=2.53e-06 — all consistent with this audit's own figures. Reclassified from `[HYPOTHESIS — unreconciled]` to `[DERIVED — explained]`. The fair comparison is if anything a *stronger* OOD signal than originally claimed: real MC20 (3.07e-06) sits right alongside in-range noise (0.9–2.5e-06) — the model's output magnitude does not distinguish a real SAR scene from correctly-scaled noise. The line suggesting the model "responds more to noise than real SAR" is retracted by its source and is not carried into this audit's conclusions.

---

### Phase 7 addendum — narrow high-activation probe `[MEASURED, this session's independent replication]`

A cross-session probe (router-datasets-ca) reported that smoothed in-range uniform noise (box blur, kernel≥9, mean≈0.5 on both channels) fires at ~0.98, with a sharp cliff versus unsmoothed noise (≈1e-6). **Independently replicated this session:**

| Input | max prob |
|---|---|
| Unsmoothed uniform noise, seed 0 | 1.06e-06 |
| Smoothed (k=9) uniform noise, seeds 0/1/2 | 0.977 / 0.986 / 0.971 |

**Refined characterization (joint finding, both sessions converging):** a perfectly **constant** (zero-variance) image at VV=VH=0.5 scores **0.0**, not 0.98 — tested directly this session. Combined with the peer's k=1 (unsmoothed noise, std~0.29) result of 0.0 and their k=9 textured channel-separation grid (std~0.042, confirming the 0.717/0.157 and 0.362/0.506 rows were genuinely textured, not flat, when they scored 0.0), the honest characterization is **band-limited texture, not smoothness**: the trigger needs spatial structure in a specific frequency band, and dies both when the input is too high-frequency (unsmoothed noise) and when it has no structure at all (constant fill). Channel-mean specificity holds on textured input at both ends of this band: MC20's and training's real channel means score 0.0 even with matching band-limited texture applied, consistent with only the ≈(0.5, 0.5)-mean region being live. Two independent replications agree on the core numbers (this session: 0.977/0.986/0.971 across 3 seeds; peer: 0.947–0.994 across 5 seeds) — about as much confidence as a synthetic probe warrants.

**Classification:** the raw numbers above are `[MEASURED]`. Any operational implication is `[HYPOTHESIS]`: this is a synthetic-input probe of model behavior, not a measured false-positive rate on real data, and it does **not** explain MC20's null result (MC20's actual channel means score 0.0 in this exact test). Test-set FP-pixel-rates remain low (0.00187 overall, 0.00509 on the lookalike hard negative), so this blind spot may be unreachable by real SAR content — unconfirmed, since no check was run for whether any real scene's channel means land near (0.5, 0.5). Recorded here as a known limitation, not as an operational risk finding.

---

## Phase 8 — Channel-Order Check `[MEASURED, effort-capped per instruction]`

Swap test (prior cross-session, reconfirmed): original max prob 3.07e-06 vs swapped 3.03e-06 (ratio 1.01). **Channel inversion is NOT SUPPORTED as the cause of MC20's null result.** The brightness-ordering anomaly from Phase 6 remains a separate, unresolved data-quality question — documented in `docs/datasets/NETRA_GOLD_V0_2.md` §10 item 9 — but it is not what is breaking MC20 inference.

---

## Phase 9 — Training-Domain Bias Audit `[MIXED]`

- **Measured:** 53% of Part I scenes are scene-level hard negatives (zero oil pixels); 82% of test tiles are empty; MC20 has 0.33–0.40× the training variance (Phase 6).
- **Blocked:** coastal/open-ocean classification, incidence-angle proxy, land fraction — no such fields exist for Zenodo Part I/II scenes, and building them would require an external GIS join, out of scope this pass.
- **Hypothesis:** the measured contrast/variance gap is consistent with NETRA-GOLD-v0.2 being a narrower, possibly curator-processed distribution relative to raw operational GRD scenes like MC20 — the textbook precondition for the OOD behavior in Phase 7. Confirming this needs Phase 5's blocked items resolved first.

---

## Phase 10 — Safety Confirmation `[DERIVED]`

Deleted = 0 · Moved = 0 · Renamed = 0 · Overwritten = 0. Frozen checkpoint byte-identical (Phase 1). `NETRA-GOLD-v0.2` and `MC20 Event Gold v0.1` both untouched. No retraining performed.

---

## Phase 11 — Recommendation `[DERIVED from measured evidence]`

**Primary: B — TRAINING_DOMAIN_EXPANSION, gated on A — PREPROCESSING_CORRECTION as a prerequisite investigation.**

- The measured variance gap and texture inversion (Phase 6) are the textbook signature of a training distribution narrower than the deployment domain — pointing at **B**.
- But **B cannot be responsibly executed** while Phase 5's blocked items (Zenodo's true raw signal representation, resolution, resampling) remain unknown: adding MC20-like scenes to a training set with an unverified, possibly-different preprocessing history risks creating a *new* inconsistency rather than closing the current one. Hence **A** (specifically, resolving what Zenodo's curators actually did) is a prerequisite, not a competing option.
- **D (architecture)** is not supported — the model performs well in-distribution (test IoU 0.6458, PR-AUC 0.8513) with clean, orderly saturation on OOD input, not erratic behavior.
- **C (domain adaptation)** is premature until A/B determine whether the gap is a fixable preprocessing artifact or a genuine content difference.
- **E (no change)** is not supported given a measured, reproducible failure on a named E2E validation event (MC20) that NETRA is meant to eventually serve.

---

## Phase 12 — Future Experiment Design `[DERIVED — design only, not executed]`

**Experiment 0 (prerequisite, no training):** reconcile Zenodo's documented resolution/calibration/processing (external dataset card) against MC20's known raw-calibrated chain. Settles whether Experiment 1's independent variable exists.

**Experiment 1 (preprocessing correction, v0.3 Gold rebuild):** if Experiment 0 finds a specific mismatch, correct it and rebuild Gold — same architecture/loss/split/epoch budget as v0.2. Success = MC20 variance ratio moves toward 1.0 **and** val IoU stays within noise of 0.6149.

**Experiment 2 (training-domain expansion):** add labeled raw-GRD scenes (not MC20) to widen the training distribution, scene-level leakage-guarded split as in v0.2. Success = new-domain val IoU improves substantially without regressing the original-domain val IoU.

**Prohibited in all future experiments:** using MC20 as a training/tuning/early-stopping signal (it has no ground-truth labels); using the 152-scene test split for anything but a final, disclosed, non-iterative check; re-fitting normalization without treating it as its own named, disclosed experiment.

---

# NETRA POST-BASELINE SCIENTIFIC AUDIT

**Official Test:** IoU=0.6458, Dice/F1=0.7848, Precision=0.8192, Recall=0.7531, PR-AUC=0.8513 (152 scenes, 2,432 tiles, threshold=0.806, single official pass)
**Checkpoint:** `netra_baseline_v02_dac482fcd84a_best.pt`, epoch 32, sha256 `9f38c690…2d2e2cd66`, verified byte-identical to frozen sidecar
**MC20 Status:** OOD / DETECTION_UNAVAILABLE (max prob 3.05e-06, indistinguishable in magnitude from synthetic noise) — not a negative oil finding
**Domain Gap:** Measured — MC20 has 0.33–0.40× training variance; normalization function/stats confirmed identical between train and MC20, so the gap is upstream of normalization
**Preprocessing Status:** Consistent where measurable (calibration→dB→clip→normalize→tile); Zenodo's own pre-publication processing is undocumented and unverifiable (`BLOCKED`)
**Channel Order:** Swap test does not support inversion as the cause of MC20's null result; a separate, unresolved brightness-ordering anomaly between train and MC20 is documented but not implicated
**Recommended Path:** **B (Training-Domain Expansion), gated on A (Preprocessing Correction) as a prerequisite**
**Next Experiment:** Experiment 0 — reconcile Zenodo's true preprocessing/resolution against MC20's documented raw-calibrated chain, before any retraining

**Do NOT retrain in this task. None performed. END.**
