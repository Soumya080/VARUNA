# NETRA Smart-Fix Investigation — Final Report

**Date:** 2026-08-30 · **Not a training task.** Checkpoint, Gold, MC20 Event Gold, and official test all unmodified.

**Classification key:** `[MEASURED]` computed this pass · `[DERIVED]` from measured facts · `[HYPOTHESIS]` unconfirmed · `[UNVERIFIABLE]` cannot be determined.

---

## 1. Objective

Determine whether a small, physically-justified, non-destructive correction to the preprocessing/input boundary can make the frozen NETRA v0.2 checkpoint deployment-compatible with the real MC20 regime, without retraining — thinking broadly rather than executing one predefined hypothesis.

---

## 2. Known Evidence

Official test: IoU 0.6458, PR-AUC 0.8513, threshold 0.806. Experiment 0/A verified the NESZ correction is implementation-correct (exact registration match) but insufficient — it collapses to identical model input via the frozen normalization's VH clip bound, and makes MC20 *more* degenerate (nodata-sentinel fraction 4.71% → 71.72%). Decision was `NESZ_IMPLEMENTATION_VALID_BUT_INSUFFICIENT`.

---

## 3. Candidate Hypotheses

A brainstorm matrix (evidence for/against, cost, reversibility, risk, information gain) was built across all 25 candidates in the prompt's list. Full detail in the JSON. Highest-priority, cheapest, most falsifiable candidate:

**R. Polarization / band semantics.** Every prior audit had flagged VV/VH band order as *unverifiable* from Zenodo's raw files and even from Zenodo's own published documentation — repeatedly noted, never closed, and explicitly distinguished from the already-falsified channel-*swap* test (which exchanged MC20's own two already-normalized channels post-hoc and found no effect — a different, downstream question from "which physical polarization did training's channel 0 actually see").

Other candidates (F/G/H contrast, C/D/E normalization interaction, I/J texture, Q sea-state) were either already characterized in Experiment A or turned out to be downstream consequences of R once tested — see Tests Performed.

---

## 4. Tests Performed

**Test 1 — Zenodo band-brightness systematicity `[MEASURED]`.** Read raw dB values from 120 real Zenodo scenes (40 each from `zenodo_part1`, `Lookalike`, `No_Oil`), deterministic sample (sorted filenames).

| Source | n | band0 mean | band1 mean | band1 brighter | gap |
|---|---|---|---|---|---|
| part1 | 40 | −31.81 dB | −19.61 dB | **100%** | +12.20 dB |
| Lookalike | 40 | −30.95 dB | −25.95 dB | **100%** | +5.00 dB |
| No_Oil | 40 | −29.75 dB | −18.12 dB | **100%** | +11.63 dB |

For natural ocean surfaces, co-pol (VV) is *always* brighter than cross-pol (VH). A 100% reversal across 120 independently-sampled scenes from three separately-collected sub-corpora is a systematic labeling error, not scene variation. **Conclusion: Zenodo band 0 is physically VH; band 1 is physically VV — the reverse of `array_provider.py::RealZenodoArrayProvider`'s assumption.**

**Test 2 — Frozen model coherence control `[MEASURED]`.** Ran the frozen checkpoint on 15 real, held-out positive-oil tiles built under the existing (mislabeled) binding: max=0.9999, mean=0.0781, oil logit mean=−6.816. **The model fires normally and strongly on real positive content under its trained convention** — its learned channel semantics are internally coherent; the problem is at MC20 *ingestion*, not in the model.

**Test 3 — Corrected-binding distribution coverage `[MEASURED]`.** Rebuilt MC20's 9-tile calibration with channel 0 ← physical VH, channel 1 ← physical VV (matching what the model actually learned), applied the *unchanged* frozen normalization, and compared 8 marginal statistics against `[P1,P99]` measured over 400 real training tiles (seed=42).

| | Current binding | Corrected binding |
|---|---|---|
| Channel-0 mean | 0.722 (outlier vs train 0.343) | 0.4585 (centrally in-range) |
| Channel-1 mean | 0.160 | 0.4497 (centrally in-range) |
| In-range statistics | — | **7 of 8** |

The one residual: channel-1 (physical VV) gradient magnitude sits ~1.5× above training's P99 — plausibly unfiltered speckle vs. a possibly-despeckled Zenodo corpus (still `[UNVERIFIABLE]`, an existing open item).

**Test 4 — Frozen model behavior, current vs. corrected `[MEASURED]`.**

| | max prob | oil logit mean |
|---|---|---|
| A current | 3.0535×10⁻⁶ | −9.624 |
| D corrected | 2.1151×10⁻⁶ | −11.013 |

The corrected binding gives a *lower*, not higher, probability. **This was not treated as failure** — per the hard rule against optimizing for probability increases, the right next question is whether this lower value is pathological or meaningful.

**Test 5 — Decisive test: is the corrected response indistinguishable from real negatives? `[MEASURED]`**

| | max prob | oil logit mean | oil logit range |
|---|---|---|---|
| Real no_oil test tiles (n=30) | 2.8685×10⁻⁶ | **−11.515** | −16.7 to −6.0 |
| Real lookalike test tiles (n=30) | 0.9716 | −10.611 | −16.3 to +1.6 |
| MC20 corrected binding | 2.1151×10⁻⁶ | **−11.013** | — |

**MC20's corrected response falls squarely inside the range of genuine, held-out, in-distribution empty-ocean tiles.** The current (uncorrected) binding's −9.624 sat noticeably closer to the edge of that range. This is the central finding of this task.

---

## 5. Small Fixes Evaluated

| Fix | Status |
|---|---|
| NESZ `floor`→`mask` (Experiment A) | Already implemented; proven to have zero effect on model input |
| `resolve_frozen_v0_2_channel_binding()` | **ACCEPTED** — see below |

---

## 6. Fixes Accepted

**`resolve_frozen_v0_2_channel_binding(physical_vv_db, physical_vh_db) -> (physical_vh_db, physical_vv_db)`**, added to `sentinel1_grd_calibration.py`. All 10 gates from Section 14 checked and passed (physical justification, correctness, backward compatibility, checkpoint/Gold/test unchanged, MC20 not used for tuning, determinism, focused tests, regression preserved).

**Category: PHYSICAL CORRECTION**, not a model-compatibility transform or optimization — it corrects a mislabeling so the frozen model's *already-learned* physical semantics are honored, introducing no new physical assumption and not tuned against MC20's output (the fix was derived entirely from Zenodo's own files and SAR physics, *before* MC20 was re-examined).

**Default behavior unchanged. Opt-in only. Not called by any production build script** (asserted in a test).

---

## 7. Fixes Rejected

- NESZ correction as a production default — verified to collapse to identical model input.
- Refitting normalization from MC20 — explicitly prohibited and scientifically invalid (no ground truth).
- Any transformation chosen for raising probability — the accepted fix was chosen *despite* lowering the raw probability, because the lower value was shown to be the meaningful one.

---

## 8. ERA5 Regime Result `[MEASURED]`

Nearest ERA5 step to T_SAR: 2023-01-15T00:00Z (2.1 min away). Wind speed over the SAR footprint at T_SAR: **mean 4.63 m/s**, min 0.35, max 7.61, P10 1.53. This is the **15th percentile of the surrounding week** (week mean 7.26 m/s), and wind is actively *decreasing* through the following hours (4.63 → 3.10 m/s over +3h).

**Verdict: CONFIRMS the calm/low-wind hypothesis.** Root-cause confidence upgraded from MEDIUM-HIGH to **HIGH**.

---

## 9. MC20 Distribution

| | Current binding | Corrected binding |
|---|---|---|
| Deviation from train (Σ\|Δmean\|) | 0.763 | **0.209** |
| Ch1 nodata fraction | 4.71% | **0.0%** |
| Marginal stats in `[P1,P99]` | outlier | **7/8** |

---

## 10. Frozen NETRA Behavior

Checkpoint, threshold, architecture all unchanged throughout. Corrected-binding MC20 output (max 2.12×10⁻⁶, logit −11.01) is statistically indistinguishable from real in-distribution empty-ocean tiles (max 2.87×10⁻⁶, logit −11.52). **This does not mean "no oil confirmed"** — it means the model's response is no longer evidence of a broken pipeline; it is a genuine, interpretable output, on par with validated behavior. Foreground fraction at 0.806 remains 0.0 throughout — not claimed as detection evidence either way, per Phase 13 discipline.

---

## 11. Root Cause

**Primary:** systematic VV/VH band-order mislabeling in `array_provider.py::RealZenodoArrayProvider` (assumes band1=VV/band2=VH; real Zenodo scenes are the reverse in 100% of 120 sampled scenes). Baked consistently into the frozen checkpoint's learned semantics *and* its normalization statistics — but MC20's ingestion followed the labels literally, creating a train/inference mismatch.

**Secondary:** genuine calm/low-wind acquisition (HIGH confidence, real ERA5), independently explaining why physical VH sits near the noise floor — real and unavoidable, accounting for the modest residual texture mismatch that remains even after the binding fix.

---

## 12. Can We Avoid Training-Domain Expansion?

# PARTIALLY

**YES** for resolving the false-OOD misclassification — the deployment-blocking symptom that MC20 looked broken. The channel-binding fix resolves this with zero retraining.

**NO** for validating positive detection in this exact calm/low-wind, near-NESZ VH regime — no labeled positive example in this regime exists anywhere in the current corpus, so there is no way, without new data, to confirm the model would correctly fire on real oil under these conditions.

---

## 13. If YES — Exact Correction

`resolve_frozen_v0_2_channel_binding()`, applied at the MC20 (or any future real, correctly-labeled Sentinel-1 source) inference boundary, immediately before `apply_netra_normalization()`, for this frozen checkpoint only. Zenodo Gold v0.2 remains untouched — its mislabeling is already baked into the checkpoint consistently; fixing `array_provider.py` only matters for a future v0.3 retrain. **Not yet applied to production `mc20_v0_1` Gold** — verified via a read-only diagnostic only, per the hard safety boundary. Applying it to a new `mc20_v0_2` is a follow-up action for the user/orchestrating session to authorize.

---

## 14. If NO — Exact Reason

N/A in full — see the qualified PARTIALLY answer above. The unresolved half is a genuine absence of labeled data in the specific operating regime, not a preprocessing question this task could close further.

---

## 15. NETRA-GOLD-v0.3 Requirements

**Priority 1:** fix `array_provider.py` at the source (band1→VH, band2→VV), carrying forward this task's evidence. **Priority 2:** Sentinel-1 GRD (IW), VV+VH with band order *verified per-file*, Sigma0-dB with one declared noise convention, **calm/low-wind (<~5 m/s) acquisitions with labeled ground truth** (the now-identified specific gap), positive and clean-negative examples in that regime, lookalikes, geographic/seasonal/geometry diversity, real timestamps.

---

## 16. NETRA-v0.3 Experiment Design

**Design only, not launched.** v0.2 control (unchanged corpus, current binding) vs. v0.3 candidate (corrected labeling + calm-sea scenes), architecture/loss/optimizer/seed/protocol held fixed. Primary success: v0.3 can be *validated* (not just observed plausible) on a held-out calm-sea slice with real labels. Secondary: source-domain metrics stay within noise of v0.2's. A new or re-verified test split is required — v0.2's test result is a historical baseline, not reused blind.

---

## 17. Safety

Deleted = 0 · Moved = 0 · Renamed = 0 · Overwritten = 0 · Checkpoint modified = 0 · v0.2 Gold modified = 0 · MC20 modified = 0 · Official test modified = 0

Calibration fidelity re-verified after the change: `max_abs_diff` vs. production MC20 Event Gold = **0.0 (exact)**. Tests: **27 passed** (5 new + 22 prior regression).

---

# FINAL DECISION

# SMALL_VALID_FIX_FOUND

The fix (`resolve_frozen_v0_2_channel_binding`) resolves the false-OOD-classification symptom without retraining, is physically justified by ironclad evidence (100% systematic reversal across 120 real scenes plus SAR physics), and moves MC20's response from a distributional outlier to statistically indistinguishable from genuine in-distribution negatives — without ever optimizing for a probability increase; in fact the accepted fix *lowers* the raw probability. It does **not** validate positive detection in this specific low-wind regime, which remains a genuine, disclosed gap requiring the training-domain expansion already specified above — but that expansion is now precisely scoped rather than open-ended.

**Not returning "training required"** without explaining why: every meaningful low-cost correction candidate was either tested to a conclusion (R: confirmed and fixed; Q: confirmed, explanatory not fixable; C/D/E: already resolved in Experiment A) or deprioritized with a stated reason (L/M/N/O/P: already UNVERIFIABLE with no new cheap evidence source available).

**END.**
 