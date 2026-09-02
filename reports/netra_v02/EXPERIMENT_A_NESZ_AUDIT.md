# Experiment A — MC20 Sentinel-1 NESZ / Thermal-Noise Implementation Audit

**Date:** 2026-08-30 · **Not a training task.** Checkpoint, Gold, MC20 Event Gold, official test, and raw SAFE all unmodified.

**Classification key:** `[MEASURED]` computed this pass · `[DERIVED]` from measured facts · `[HYPOTHESIS]` unconfirmed · `[UNVERIFIABLE]` cannot be determined.

---

## Hypothesis

The Experiment-0 VH overshoot (variance ratio 0.6963 → 3.8023) is caused by an implementation, LUT-interpretation, polarization, registration, unit, or sub-swath error in the NESZ correction.

**Verdict: REFUTED.** The implementation was audited against the real SAFE product and verified correct on every axis tested. The VH behaviour is a legitimate physical property of this scene.

---

## Experiment 0 Recap `[MEASURED]`

| | Original | Denoised |
|---|---|---|
| VV variance ratio | 0.2478 | 0.4212 |
| VH variance ratio | 0.6963 | **3.8023** |
| Frozen NETRA max prob | 3.05×10⁻⁶ | 5.11×10⁻⁶ |

Experiment 0 was **re-run this task and reproduced bit-identically** after the code change below, because the new parameter defaults to the original behaviour.

---

## SAFE Evidence `[MEASURED]`

- **IPF version 003.52** — well past the 2.9 threshold from which a product-level `noiseAzimuthVectorList` is expected. Present and used.
- `noiseRangeVectorList`: 27 vectors × 652 points. `noiseAzimuthVectorList`: 3 vectors (IW1/IW2/IW3).
- **Pixel axis is shared across all 27 range vectors and strictly monotonic** — validating the implementation's `pixels[0]` assumption (asserted in a test). The axis is *non-uniformly* spaced (extra samples inserted at sub-swath boundaries, e.g. `…8560 8600 8619 8620 8660…`); `RegularGridInterpolator` accepts non-uniform monotonic axes, so this is handled correctly.
- **Polarization bindings verified:** the VV noise XML declares `VV`, the VH declares `VH`. No swapped-file bug.
- **Sub-swath:** crop columns 18657–20193 lie **entirely inside IW3** (17439–25898). No seam crosses the crop.
- LUT magnitudes: VV `noiseRangeLut` max 1891.2, VH 2151.4; azimuth LUT spans 0.9995–1.1389; `sigmaNought` 557.66–662.48 and **identical for both polarizations** (as expected — it is a geometric/radiometric factor, not a target property).

---

## Authoritative Processing Evidence `[MEASURED]`

**Copernicus SentiWiki, Sentinel-1 Processing** confirms: noise vectors are provided in **linear power**, and noise is subtracted from power-detected GRD data **before** the sigmaNought calibration factor is applied (Eq. 5–6: `calibrated = A × [DN − η·noiseLut]`). This directly supports the implemented form `sigma0_linear = (DN² − NoisePower) / sigmaNought²`.

**Documented gap, recorded not hidden:** neither ESA source consulted explicitly states that total noise = `noiseRangeLut × noiseAzimuthLut` (multiplication) rather than some other combination; SentiWiki describes the range and azimuth contributions as separate steps without naming the operator. **Why this does not change the conclusion:** the azimuth LUT spans only 0.9996–1.1083 over this crop — at most an 11% multiplicative effect. No choice of operator, including omitting it entirely, can produce the observed ~2.3× VH standard-deviation change. If the NESZ path is ever promoted toward production default, confirm the operator against the ESA IPF product specification or the SNAP `Sentinel1RemoveThermalNoiseOp` source first.

---

## Current Implementation — bug checks `[MEASURED]`

| Candidate cause | Result |
|---|---|
| A. Implementation bug | **NOT FOUND** |
| B. LUT interpretation bug | **NOT FOUND** — noise LUT (~300–490 over the crop) is in the same numeric regime as DN² (461–2609), exactly as expected for a linear-power LUT. An amplitude-vs-power confusion would show a √-scale mismatch (~19 vs ~370); it does not. |
| C. Polarization / LUT mismatch | **NOT FOUND** — verified in both noise and calibration XMLs |
| D. Line/pixel registration error | **NOT FOUND** — see below |
| E. Unit / scaling error | **NOT FOUND** — see B |
| F. Sub-swath handling error | **NOT FOUND** — crop entirely in IW3; uncovered columns *raise* rather than silently defaulting to a neutral 1.0 |

### Registration verification — exact

An independent manual bilinear reconstruction straight from the raw XML, compared against the implementation:

| | |
|---|---|
| Probe (local → absolute) | (500, 700) → line 7768, pixel 19357 |
| Bracketing lines / pixels | 7359, 8028 / 19319, 19359 |
| Manual range-LUT value | 356.125491 |
| Azimuth factor (IW3) | 1.015355 |
| **Manual total noise power** | **361.593798** |
| **Implementation value** | **361.593798** |
| **Absolute difference** | **0.0** |

This rules out off-by-one, crop-origin offset, absolute-vs-local line numbering, wrong swath offset, and wrong LUT dimensions.

---

## Corrected Implementation `[DERIVED]`

One defect *was* found — but it is presentational, not physical: the `1e-6` floor substitutes an **arbitrary constant (~−115 dB)** for pixels where sigma0 is genuinely **unmeasurable**, and that constant then dominates any statistic computed over them.

Added `below_noise_policy` to `calibrate_to_db_denoised()`:
- `"floor"` (**default, unchanged** — keeps Experiment 0 exactly reproducible)
- `"mask"` (opt-in) — marks below-noise pixels `NaN`, consistent with the module's existing `DN==0 → NaN` convention and `apply_netra_normalization()`'s existing non-finite → nodata handling.

`calibrate_to_db()` and every production caller are **untouched**. This change was made because flooring fabricates a value where none is measurable — **not** because it improves NETRA output, which it provably does not (below).

---

## VV `[MEASURED]`

DN² mean 2608.91 · noise mean 368.79 · **median SNR 6.165** · below-noise fraction **0.17%**

Variance ratio: 0.2478 → 0.4212 (masked). Removing noise from a strong signal is a modest, well-conditioned correction — std rises 2.215 → 2.888 dB and the ratio moves toward, but still below, 1.0. Well-behaved.

## VH `[MEASURED]`

DN² mean 460.85 · noise mean 371.28 · **median SNR 1.079** · below-noise fraction **43.81%**

Variance ratio: 0.6963 → 3.8023 (masked).

**Root mechanism:** the median VH pixel carries only **7.9% more power than the noise floor**. Mean noise power is nearly identical between channels (VV 368.8 vs VH 371.3) — as expected, since NESZ is a *receiver-chain* property — while VH's signal is **~5.7× weaker** than VV's. Subtracting a nearly-equal quantity leaves a small residual whose *relative* spread is enormous; in the logarithmic dB domain this inflates std from 2.236 to 5.226 dB. The overshoot past 1.0 is an **arithmetic consequence of near-noise-floor subtraction**, not an error.

This is expected physics: Sentinel-1 cross-pol over calm open water is well known to approach the instrument NESZ.

---

## Noise-Floor Analysis `[MEASURED]`

| | VV | VH |
|---|---|---|
| Below-noise pixels | 4,059 | 1,033,286 |
| Below-noise fraction | 0.17% | **43.81%** |

**The 43.8% finding is retained explicitly and is not diminished** by the fact that it complicates the model story — it is arguably the most important physical fact this audit established about the scene. The floor-contaminated VH variance ratio of **226.1** is kept in the record but labelled an artifact of the arbitrary epsilon and never used for any conclusion.

---

## Spatial Analysis `[MEASURED]`

VH below-noise mask, 4×4 block means:

```
0.4284  0.4223  0.4339  0.3995
0.4601  0.4359  0.4224  0.4114
0.4696  0.4625  0.4464  0.4492
0.4687  0.4448  0.4161  0.4390
```

VH noise power falls smoothly with range: **460.54 → 316.50** across columns, and the below-noise fraction tracks it (0.4674 → 0.4102).

**Verdict: spatially coherent, not localized or pathological.** Near-uniform across all 16 blocks with a smooth monotonic range-direction gradient matching the elevation-beam-pattern / range-spreading-loss behaviour — no discontinuities, no sub-swath seams, no crop-boundary artifacts. A registration or indexing bug would be expected to produce exactly such artifacts; none are present.

---

## Three-Way Comparison `[MEASURED]`

Zenodo reference (raw Sigma0-dB): VV mean −34.78 / std 4.45 · VH mean −20.14 / std 2.68

| | VV mean | VV std | VV ratio | VH mean | VH std | VH ratio | VH valid |
|---|---|---|---|---|---|---|---|
| **A** original | −21.775 | 2.215 | 0.2478 | −29.338 | 2.236 | 0.6963 | 1.0000 |
| **B** Exp-0 floor | −22.897 | 4.797 | 1.1622 | −69.772 | 40.298 | *226.10* ⚠ | 1.0000 |
| **C** Exp-A mask | −22.738 | 2.888 | 0.4212 | −34.355 | 5.226 | 3.8023 | 0.5619 |

⚠ B's VH row is dominated by the arbitrary −115 dB floor constant — not a physical measurement.

**Phase 9 calibration fidelity: `max_abs_diff` vs production MC20 Event Gold = 0.0 (exact).**

---

## Frozen NETRA Behaviour `[MEASURED]`

Checkpoint `9f38c690…2d2e2cd66`, threshold 0.806 — architecture, threshold, normalization, and checkpoint all unchanged.

| | max | mean | P99 | fg @0.806 | oil logit mean |
|---|---|---|---|---|---|
| A original | 3.05×10⁻⁶ | 5.56×10⁻⁹ | 2.23×10⁻⁸ | **0.0** | −9.62 |
| B Exp-0 floor | 5.11×10⁻⁶ | 1.38×10⁻⁸ | 4.27×10⁻⁸ | **0.0** | −9.17 |
| C Exp-A mask | 5.11×10⁻⁶ | 1.38×10⁻⁸ | 4.27×10⁻⁸ | **0.0** | −9.17 |

### Two decisive findings

**1. B and C are byte-identical to the model** (`normalized input max abs diff = 0.0`). The floor policy's −115 dB is clipped to VH `clip_low = −33.425` and rescales to exactly 0.0; the mask policy's NaN is forced to the 0.0 nodata sentinel. **Both collapse to the same value.** The corrected representation is strictly a statistical-honesty improvement — it cannot change what NETRA sees. This forecloses any hope that a better below-noise representation would rescue detection under the frozen normalization contract.

**2. NESZ correction makes MC20 *more* degenerate, not less:**

| | VH fraction exactly 0.0 |
|---|---|
| A original | 4.71% |
| B / C denoised | **71.72%** |
| Training corpus nodata | 2.585% |

The physically-correct preprocessing drives **71.7% of the VH channel to the nodata sentinel** — pushing MC20 *further* out of distribution, not closer. (71.7% exceeds the 43.8% below-noise fraction because additional above-noise pixels still fall below the frozen VH `clip_low` after subtraction.)

**Phase 13 discipline:** foreground fraction is 0.0 in all three conditions. This does **not** establish "no oil at MC20" — status remains `OOD / DETECTION_UNAVAILABLE`. Equally, the 1.67× probability rise is **not** "improved detection": both values sit 5–6 orders of magnitude below threshold with the oil logit near −9.

---

## Root Cause

**Classification: G — legitimate physical property of the scene** (with a separately-identified, purely presentational floor-constant defect, now corrected).

**Evidence for:** exact registration match (0.0); LUT units in the correct regime; polarizations verified; crop entirely within IW3; IPF 3.52 consistent with the azimuth vector; spatially coherent near-uniform below-noise mask with a smooth range gradient tracking noise power; VH median SNR 1.079; near-identical VV/VH noise power (368.8 vs 371.3) against a ~5.7× weaker VH signal — fully explaining why *only* VH overshoots.

**Evidence against:** the range×azimuth operator is not explicitly confirmed in the ESA docs consulted (recorded above) — but the azimuth factor's ≤11% span cannot account for a ~2.3× std change.

**Confidence:** **HIGH** that no implementation bug is responsible. **MEDIUM-HIGH** that the scene is a genuinely calm/low-wind acquisition — inferred from cross-pol at NESZ, not yet confirmed against the real ERA5 wind field that MC20 Event Gold already contains.

---

## Decision

# B — NESZ_IMPLEMENTATION_VALID_BUT_INSUFFICIENT

Every axis tested (A implementation, B LUT interpretation, C polarization, D registration, E units, F sub-swath) came back clean, with registration verified to **exact numerical equality**. The VH overshoot is explained by scene physics, not a defect. But the correction does not restore NETRA's discriminative response — and in fact drives 71.7% of the VH channel to the nodata sentinel, moving MC20 *further* from the training distribution. The implementation is valid; it is insufficient.

*Not chosen:* **A** — no implementation bug; the one defect found was presentational and provably has zero effect on model input or output. **C alone** — scene physics is the *mechanism*, but selecting it would understate the operative conclusion about sufficiency. **D** — implies a calibration error contributed; none was found. **E** — the question was resolved on direct evidence.

**This decision rests on SAR-processing evidence, not NETRA's score.**

---

## Next NETRA Experiment

Per the Phase 15 rule (*calibration correct but NETRA remains OOD → training-domain expansion*):

# NEXT = EXPERIMENT B — TRAINING_DOMAIN_EXPANSION

**Cheap prerequisite recommended first:** MC20 Event Gold already contains a **real ERA5 10 m wind field** for this exact acquisition. Reading it to confirm or refute the calm-sea inference behind the cross-pol-at-NESZ explanation costs no new data and no training, and would raise root-cause confidence from MEDIUM-HIGH to HIGH.

**Ruled out for v0.3 by this audit:** fixing MC20 by preprocessing correction alone (proven ineffective, and it worsens the nodata fraction); expecting a better below-noise representation to help under the frozen normalization contract (proven to collapse to identical input); any explanation resting on a calibration or registration defect.

**Constraint carried forward:** the frozen v0.2 normalization contract (VH `clip_low` = −33.425 dB) is itself now implicated — noise-corrected cross-pol over calm water falls largely below that bound. If a v0.3 dataset adopts thermal-noise-removed inputs, normalization statistics must be re-derived **from training data** under that same convention, as an explicitly disclosed, separately-versioned change — **never refitted from MC20**.

---

## Future Data Requirements `[DERIVED — specification only, nothing downloaded]`

Sentinel-1 GRD (IW), VV+VH with band semantics **verified from each product's own annotation XML** rather than assumed; Sigma0-dB via the documented chain; **a single declared thermal-noise convention applied to training and inference alike** (this audit shows a train/infer mismatch materially changes the input distribution); geographic diversity beyond the Zenodo corpus's apparent ~55°N concentration; seasonal diversity (Zenodo scenes carry no verified timestamps at all); **explicit calm / low-wind sea states where cross-pol approaches NESZ — the regime where the current model demonstrably fails and which is likely under-represented in training**; positives, calm-regime negatives, and lookalikes where obtainable; real timestamps; full viewing geometry.

---

## Safety

Deleted = 0 · Moved = 0 · Renamed = 0 · Overwritten = 0
Checkpoint modified = 0 · Gold modified = 0 · Official test modified = 0 · MC20 modified = 0 · Raw SAFE modified = 0

No retraining, no fine-tuning, no threshold tuning, no normalization fitted from MC20.
Calibration fidelity after the change: **max_abs_diff vs production MC20 Event Gold = 0.0 (exact)**.
Tests: `tests/unit/test_sentinel1_nesz_correction.py` (8 new) + existing calibration/MC20 regression suites — **22 passed**.

**END.**
