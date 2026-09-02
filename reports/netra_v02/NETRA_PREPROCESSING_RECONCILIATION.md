# NETRA Preprocessing Reconciliation & Root-Cause Diagnosis

**Date:** 2026-08-30 · **Git commit:** `67b16a7` · **Role:** Root-cause diagnosis and NETRA v0.3 experiment design. **No training, no downloads, no Gold modification performed.**

**Classification key:** `[MEASURED]` computed this pass from real code/data/external sources · `[DERIVED]` computed from measured facts · `[HYPOTHESIS]` plausible, unconfirmed · `[UNVERIFIABLE]` cannot be determined with evidence available, anywhere.

---

## BASELINE

Official test (152 scenes, 2,432 tiles, threshold=0.806, unchanged since the prior audit — **not re-run this pass**, existing artifact verified intact instead): IoU=0.6458, Dice/F1=0.7848, Precision=0.8192, Recall=0.7531, PR-AUC=0.8513.

Checkpoint `netra_baseline_v02_dac482fcd84a_best.pt`, epoch 32, sha256 `9f38c690…2d2e2cd66` — unchanged, byte-identical.

---

## MC20

Status: `OOD / DETECTION_UNAVAILABLE`. Max oil probability ≈ 3.05×10⁻⁶. **Not** interpreted as "no oil" — interpreted only as "the frozen baseline did not produce a trustworthy detection on this input."

---

## ZENODO PIPELINE — reconstructed from code and, this pass, from the original data provider

Traced: `zenodo_adapter.py::ZenodoAdapter.discover()` → `array_provider.py::RealZenodoArrayProvider.load_channels()` → stages 01–04.

**New this pass:** the original Zenodo dataset records (8346860, 8253899) were fetched directly from zenodo.org to answer questions this repo's own files cannot answer.

| Question | Answer | Basis |
|---|---|---|
| What quantity is stored? | **Sigma0, in decibels** | `[MEASURED, external]` — Zenodo's own published description |
| Calibration already performed? | **Yes** | `[MEASURED, external]` |
| dB conversion already performed? | **Yes** | `[MEASURED, external]` |
| Clipping applied by source? | `[UNVERIFIABLE]` | not stated |
| Resolution/GSD stated by source? | `[UNVERIFIABLE]` — only "2048×2048×2" given | `[MEASURED, external]` for what IS stated |
| Resampling performed? | `[UNVERIFIABLE]`, but circumstantially plausible (uniform chip size vs. GRD's native ~25,000×17,000) | `[HYPOTHESIS]` |
| VV/VH band order? | **Unverifiable even by the original authors** — Zenodo states both polarizations are present, never which band is which | `[MEASURED, external]` that this is genuinely undocumented, not just missing from this repo |
| scale/offset tags in the GeoTIFF? | `(1.0, 1.0)` / `(0.0, 0.0)` — no rescaling encoded | `[MEASURED]` |
| Incidence angle / orbit / look direction? | Not present in the curated GeoTIFFs | `[MEASURED]` |
| Original documentation stored locally? | No — fetched live this pass | `[MEASURED]` |

**A documentation-accuracy finding, not previously reported:** `sentinel1_grd_calibration.py`'s docstring justifies skipping terrain correction by claiming this is "consistent with how Zenodo's source imagery is delivered, **per the existing Gold manifest's `source_product` field**." **That field does not exist anywhere in `data/manifests/netra_gold_v0_2.json`** — checked directly this pass. The underlying claim (Zenodo being GRD-derived Sigma0-dB) is independently confirmed true by this pass's external fetch, but the comment cites evidence that isn't there. Worth a one-line doc fix pointing at the real evidence source instead — not treated as a defect requiring a contracts change, since it's a code comment, not a contract.

---

## MC20 PIPELINE — confirmed from code

`sentinel1_grd_calibration.py`: real DN crop → `parse_calibration_lut()` (real XML parse) → `_interpolate_lut_to_grid()` (bilinear) → `calibrate_to_db()`: **sigma0_linear = DN² / sigmaNought²; dB = 10·log₁₀(sigma0_linear)** → `apply_netra_normalization()` (frozen v0.2 clip/scale, identical function and stats as training) → `tile_512()`.

**Explicitly not done, per the module's own docstring:** thermal-noise (NESZ) removal (`thermal_noise_removed=False`, always), terrain correction, speckle filtering.

---

## EARLIEST COMMON REPRESENTATION

**Selected: calibrated Sigma0, dB scale (pre-normalization).** This pass confirms both datasets are independently verified to share this representation (Zenodo per the external fetch, MC20 per its calibration code) — comparing raw DN would not be valid (different quantities), and comparing post-normalization `[0,1]` values (done in the prior audit) compresses real dB differences through a shared clip+rescale.

**Method:** Zenodo — raw dB pixel values read directly from 10 sampled GeoTIFFs. MC20 — the 9 Gold tiles' `[0,1]` values inverted back to dB using the exact frozen clip bounds (reproduces the pre-normalization array exactly).

| | Zenodo (10 scenes) | MC20 (9 tiles) | Variance ratio (MC20/Zenodo) |
|---|---|---|---|
| VV mean / std (dB) | −34.78 / 4.45 | −21.78 / 2.18 | **0.24** |
| VH mean / std (dB) | −20.14 / 2.68 | −29.29 / 2.11 | **0.62** |

**Key observation:** the compression is **not uniform across channels** — VV compresses to 24% of training variance, VH to 62%. A single channel-independent cause (e.g. thermal-noise removal alone) would be expected to affect both channels more similarly; this asymmetry keeps the channel-semantics question (below) live as a contributing factor, not fully separable from a pure preprocessing explanation.

---

## RESOLUTION

`[MEASURED]`: Zenodo's GeoTIFFs use `EPSG:4326` with an *identical* degree-based pixel spacing (8.983×10⁻⁵°) on both axes — the standard "10 m at the equator" constant, applied uniformly regardless of latitude. At the sampled scenes' ~55.2–55.5°N, this yields ~10.00 m true spacing in latitude but only **~5.7 m in longitude** — a ~1.75× anisotropic ground sample distance from using an uncorrected degree increment.

**Direction check:** if Zenodo chips were downsampled from native GRD resolution, that would *reduce* Zenodo's variance relative to a native-resolution MC20 — the *opposite* of the observed direction (MC20 has lower variance). Combined with MC20's *higher* gradient-magnitude texture despite lower global variance (prior audit, Phase 6), simple resampling/blur does not look like the primary explanation in either direction. **Conclusion: `UNKNOWN` as the primary cause.**

---

## GEOMETRY

Zenodo's uniform degree-spacing georeferencing is a real, measured inconsistency with MC20's orbit/geolocationGridPoint-derived georeferencing. This affects claimed pixel position and aspect ratio — **no mechanism was identified by which it would alter stored backscatter values or their variance.** Recorded as a genuine finding, not currently linked to the OOD failure.

---

## BAND SEMANTICS — kept separate as instructed

**A. Channel inversion:** `NOT SUPPORTED` (swap test: 3.07e-06 vs 3.03e-06, ratio 1.01) — not re-litigated per instruction.

**B. Source-band semantic uncertainty:** `CONFIRMED UNVERIFIABLE — now at the source-documentation level.` This pass's external fetch shows Zenodo's own authors never state which GeoTIFF band is VV vs. VH. This project's code resolves the ambiguity via an unverified assumption. A and B are answering different questions (A: does the assumption matter to the model? — no. B: is the assumption actually correct? — unknown, and unknowable from any evidence located).

---

## ROOT CAUSE

| Cause | Verdict | Confidence |
|---|---|---|
| REPRESENTATION_MISMATCH | **NOT SUPPORTED** — both confirmed Sigma0-dB, same normalizer | HIGH (ruled out) |
| PREPROCESSING_MISMATCH | **SUPPORTED** — MC20 lacks thermal-noise removal (code-confirmed); Zenodo's status unverifiable but plausible | MEDIUM |
| GEOMETRY_SHIFT | Measured as present; no mechanism linking it to the value gap | LOW (as cause of the gap) |
| DATASET_SOURCE_SHIFT / TRAINING_DOMAIN_LIMITATION | **SUPPORTED** — narrow, imbalanced training corpus; plausible independent contributor | MEDIUM |
| MODEL_LIMITATION | **NOT SUPPORTED** — clean in-distribution performance, orderly OOD saturation | HIGH (ruled out) |
| RESOLUTION_MISMATCH | Direction-inconsistent with the simple version of this hypothesis | LOW |

**Overall: `MIXED_CAUSE`**, led by **PREPROCESSING_MISMATCH** (thermal-noise-removal asymmetry) as the single most actionable, falsifiable hypothesis, with **TRAINING_DOMAIN_LIMITATION** as a plausible compounding contributor. Representation mismatch and model limitation are ruled out with high confidence.

---

## NETRA v0.3 DATA STRATEGY

**Not B outright.** The evidence supports running the **cheapest falsifying experiment first** — a code-level calibration correction requiring **zero new data and zero retraining** — before committing to the much larger, harder-to-reverse step of acquiring and labeling new Sentinel-1 GRD scenes.

---

## DATA ACQUISITION SPEC — only if Experiment 0 fails to close the gap

Sentinel-1 GRD (IW), VV+VH with **verified** (not assumed) band order at ingestion, Sigma0-dB **with thermal-noise removal applied consistently**, geographically diverse beyond Zenodo's apparent ~55°N bias, multi-season, explicit calm/low-wind sea-state coverage, real acquisition timestamps and full viewing geometry (all of which Zenodo's current pipeline lacks). Positive, negative, and lookalike examples all needed if pursued. **Nothing downloaded — specification only.**

---

## NETRA v0.3 EXPERIMENT PLAN

**Experiment 0 (run first, no training, no new data):** Apply MC20's already-present-but-unused NESZ noise LUT (`annotation/calibration/noise-*.xml`) before dB conversion; re-measure the VV/VH variance ratio and the frozen model's MC20 output probability. **Success:** ratio moves substantially toward 1.0 and/or model output exits the noise-indistinguishable regime. **Failure:** no material change → shifts weight to domain expansion.

**Experiment A (gated on Experiment 0's success):** Apply the corrected calibration contract to MC20-side inference only; re-evaluate the frozen (or lightly retrained) checkpoint. Test set touched only as a disclosed second official evaluation if needed. Fixed: architecture, seed=42, optimizer=AdamW, v0.2 split, frozen normalization stats unless explicitly revised as its own disclosed sub-experiment.

**Experiment B (gated on Experiment A's failure):** Add labeled, non-MC20 raw-GRD scenes per the acquisition spec, scene-level leakage-guarded split matching v0.2's methodology. MC20 remains a qualitative check only, never a training/tuning signal.

**Prohibited throughout:** MC20 as a training/tuning/early-stopping/threshold signal; the 152-scene test split for anything but a disclosed, non-iterative final check; silent re-fitting of normalization.

---

## LOCKED EVALUATION PROTECTION

Official test: `LOCKED_FOR_FINAL_EVALUATION`, unchanged, not re-touched this pass. MC20: `EXTERNAL EVALUATION / OOD DIAGNOSTIC`, unchanged. Neither used to select any v0.3 hyperparameter in this design.

---

## SAFETY

Deleted=0, Renamed=0, Moved=0, Overwritten=0, Frozen checkpoint modified=0, Official test modified=0, MC20 modified=0, NETRA-GOLD-v0.2 modified=0. Files touched: three new report files only. No training launched, no data downloaded, no Gold modified.

---

# NETRA v0.2 → v0.3 SCIENTIFIC DECISION REPORT

## Baseline
official test: IoU=0.6458, Dice/F1=0.7848, PR-AUC=0.8513 (152 scenes, 2,432 tiles)
checkpoint: `netra_baseline_v02_dac482fcd84a_best.pt`, epoch 32, sha256 `9f38c690…2d2e2cd66`
threshold: 0.806

## MC20
status: OOD / DETECTION_UNAVAILABLE
max probability: 3.05×10⁻⁶
interpretation: not evidence about MC20's oil state; the input falls outside the model's discriminative range

## Preprocessing
Zenodo: Sigma0-dB, calibration + dB conversion confirmed already applied by the source (external fetch, this pass); resolution/resampling/band-order unverifiable even at the source
MC20: real DN→sigma0→dB calibration, explicitly **no** thermal-noise removal, no terrain correction, no speckle filtering
comparison: same representation and same normalizer (confirmed) — the gap is upstream, most plausibly in the noise-removal asymmetry

## Distribution Gap
VV: −34.78dB (std 4.45) train vs. −21.78dB (std 2.18) MC20 — variance ratio 0.24
VH: −20.14dB (std 2.68) train vs. −29.29dB (std 2.11) MC20 — variance ratio 0.62
variance ratio: asymmetric across channels (0.24 vs 0.62) — inconsistent with a single uniform cause
contrast: MC20 has lower global variance but *higher* pixel-gradient texture than training — inconsistent with simple resampling/blur

## Root Cause
primary: PREPROCESSING_MISMATCH (thermal-noise-removal asymmetry) — MEDIUM confidence
secondary: TRAINING_DOMAIN_LIMITATION — MEDIUM confidence
confidence: MIXED_CAUSE overall; REPRESENTATION_MISMATCH and MODEL_LIMITATION ruled out (HIGH confidence)

## Recommended Data Change
None yet — run Experiment 0 (thermal-noise correction, zero new data) before deciding

## Required New Dataset Characteristics
Sentinel-1 GRD, VV+VH with verified band order, Sigma0-dB with consistent noise removal, geographically/seasonally/sea-state diverse — specification only, contingent on Experiment 0's outcome

## NETRA v0.3 Experiment
Experiment 0 → gates Experiment A → gates Experiment B (see full plan above)

## Locked Evaluation Protection
Official test LOCKED_FOR_FINAL_EVALUATION; MC20 EXTERNAL/OOD DIAGNOSTIC; neither used for v0.3 tuning

## Safety
Deleted=0, Renamed=0, Moved=0, Overwritten=0, Frozen checkpoint modified=0, Official test modified=0, MC20 modified=0

## FINAL DECISION

**E — FURTHER_INVESTIGATION_REQUIRED**

Re-evaluated from evidence, not defaulted to the prior recommendation (B): this pass surfaced a specific, cheap, zero-new-data falsifying experiment (thermal-noise-removal correction) that has not yet been run. Choosing B now risks acquiring and labeling new data to fix a gap that a code-level calibration fix might substantially close. Choosing A alone would be premature given the channel-asymmetric variance compression, which suggests the true picture may be mixed-cause rather than pure preprocessing.

## EXACT NEXT ACTION

**Run Experiment 0: apply MC20's already-present NESZ thermal-noise LUT (`annotation/calibration/noise-*.xml`, currently parsed by nothing) to the calibration chain, re-measure the VV/VH variance ratio against Zenodo's raw-dB statistics, and re-run the frozen checkpoint's inference on the corrected tiles.** No training, no new data, no Gold modification required. This single measurement determines whether Experiment A (preprocessing-only) or Experiment B (domain expansion) is the justified next step.
