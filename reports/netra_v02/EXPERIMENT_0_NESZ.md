# NETRA Experiment 0 — NESZ / Thermal-Noise Falsification

**Date:** 2026-08-30 · **Not a training run.** Checkpoint, Gold, MC20 Event Gold, official test, and the raw SAFE product are all unmodified.

**Classification key:** `[MEASURED]` computed this pass · `[DERIVED]` computed from measured facts · `[HYPOTHESIS]` unconfirmed · `[UNVERIFIABLE]` cannot be determined.

---

## Hypothesis

Applying MC20's existing-but-unused Sentinel-1 NESZ thermal-noise LUT to its calibration chain materially reduces the Zenodo↔MC20 distribution gap and/or moves the frozen NETRA v0.2 checkpoint's MC20 output out of its current numerical-floor (OOD-saturated) regime.

## Pre-registered decision criterion (fixed before seeing the denoised result)

- **Criterion i:** either channel's variance ratio (denoised-MC20 / Zenodo-raw-dB) increases by ≥0.15 absolute versus the original ratio.
- **Criterion ii:** the frozen model's max oil probability across the 9 denoised tiles increases ≥1000× relative to the original 3.05×10⁻⁶.
- **Rule:** `material_effect = criterion_i OR criterion_ii`.

---

## Phase 1 — Existing calibration + noise LUT inspection `[MEASURED]`

Traced `sentinel1_grd_calibration.py`: DN → `parse_calibration_lut()` → `_interpolate_lut_to_grid()` → `calibrate_to_db()` (sigma0=DN²/sigmaNought², dB=10log₁₀). Inspected both `annotation/calibration/noise-*-vv-*.xml` and `-vh-*.xml`: each contains a `noiseRangeVectorList` (27 vectors, same line/pixel grid convention as calibration, field `noiseRangeLut`) and a `noiseAzimuthVectorList` (3 vectors, one per IW sub-swath, each a 1D function of azimuth line only). The crop window (columns 18657–20193) was verified to fall entirely within IW3's coverage.

## Phase 2 — Minimal opt-in correction `[DERIVED]`

Added `calibrate_to_db_denoised()` as a new, additive sibling function in `sentinel1_grd_calibration.py`. **`calibrate_to_db()` and every existing caller (`scripts/build_mc20_event_gold.py`) are byte-unchanged.** No default behavior was altered.

Formula: `NoisePower(line,pixel) = noiseRangeLut(line,pixel) × noiseAzimuthLut(line)`; `sigma0_linear = max(DN² − NoisePower, 1e-6) / sigmaNought²`; `dB = 10·log₁₀(sigma0_linear)`.

## Phase 3 — Experiment artifact `[MEASURED]`

`reports/netra_v02/experiment0_nesz/experiment0_nesz_raw.json` — includes source SAFE/LUT/checkpoint/manifest SHA-256 checksums, git commit, crop window, and every measurement below.

**Fidelity check performed before trusting anything else:** this script's independently-reconstructed "original" calibration path was compared against the real, on-disk MC20 Event Gold v0.1 tiles. **Max absolute difference: 0.0 — exact reproduction.**

## Phase 4 — Pre-normalization comparison `[MEASURED]`

| | Original | Denoised (floor-excluded, fair) |
|---|---|---|
| VV mean/std (dB) | −21.77 / 2.22 | −22.74 / 2.89 |
| VH mean/std (dB) | −29.34 / 2.24 | −34.35 / 5.23 |
| VV variance ratio vs. Zenodo | 0.2478 | **0.4212** |
| VH variance ratio vs. Zenodo | 0.6963 | **3.8023** |

**A methodological issue was found and corrected during this run, not silently absorbed:** the `1e-6` floor substitutes for pixels where `DN² < NoisePower` (a real physical outcome — thermal noise exceeds true signal there) but is an *arbitrary floor value*. Including floored pixels in the variance calculation lets that arbitrary choice dominate the statistic — the raw (floor-included) VH variance ratio was a physically implausible **226×**, an artifact, not a finding. All decision-relevant numbers above **exclude** floored pixels for a fair comparison; the contaminated figures are retained in the JSON only for transparency, explicitly labeled `DO_NOT_USE_FOR_DECISION`.

**A genuine, independent headline finding:** **43.8% of this MC20 crop's VH pixels have signal power below the sensor's own real, product-supplied noise floor.** This is true regardless of any modeling choice made here — nearly half the VH channel's dynamic range in this specific scene is physically noise-limited.

## Phase 5 — Frozen model probe `[MEASURED]`

Checkpoint, threshold (0.806), architecture, and normalization all unchanged.

| | Original | Denoised |
|---|---|---|
| Max oil probability | 3.05×10⁻⁶ | 5.11×10⁻⁶ |
| Ratio | — | **1.67×** |

Both values sit 5–6 orders of magnitude below the operating threshold, in the same numerical-floor regime. **The frozen model's behavior is practically unchanged.**

## Phase 6 — Pre-registered decision, applied mechanically `[DERIVED]`

- Criterion i: VV delta=0.173, VH delta=3.106 → **MET**
- Criterion ii: ratio=1.67× (need ≥1000×) → **NOT MET**
- Rule result: `material_effect = TRUE` → mechanically, **proceed to EXPERIMENT A**

**Substantive caveat, stated plainly rather than smoothed over:** the registered rule fired *only* on criterion i, and criterion i's own result is not a clean win — VH didn't converge toward 1.0, it **overshot past it by nearly 4×**, moving further from a "matches training" story in the opposite direction. Criterion ii — arguably the more decision-relevant signal, since it measures whether the actual practical problem (saturated model output) improves — showed **no material change at all**. This is reported as a genuine, unresolved ambiguity, not resolved by picking whichever reading looks better. The pre-registered rule is honored as stated (no re-thresholding after seeing results), but the interpretation is: **weak, mixed positive — not a clean confirmation.**

## Phase 7 — No retraining `[DERIVED]`

Confirmed: no training launched, no Gold rebuilt, no threshold tuned.

## Phase 8 — Decision tree

Mechanical next step per the registered rule: **EXPERIMENT A**, but scoped narrowly — specifically investigating *why VH overshoots* (candidates: the still-unresolved channel-semantics uncertainty from the prior audit; a possible gap in the azimuth-noise combination as implemented here; or a genuine, correctly-measured property of this specific scene/date) — and re-running the frozen-model probe afterward, since this pass shows NESZ correction alone does not move the model out of saturation.

## Phase 9 — Future data spec

Not triggered this pass (routes to A, not B). Remains valid and unchanged if Experiment A itself fails — see `reports/netra_v02/NETRA_PREPROCESSING_RECONCILIATION.md`.

## Phase 10 — Test protection `[DERIVED]`

Official test untouched. MC20 used only for distribution/output measurement, never as a tuning source — no threshold, hyperparameter, or model selection was based on it.

## Safety

Deleted=0, Moved=0, Renamed=0, Overwritten=0, Checkpoint modified=0, Gold modified=0, MC20 modified=0, Official test modified=0, Raw SAFE modified=0. New files only: one additive function set in `sentinel1_grd_calibration.py`, one new experiment script, three new report files.

---

# NETRA EXPERIMENT 0 REPORT

**Hypothesis:** NESZ correction alone materially closes the Zenodo↔MC20 gap and/or restores non-saturated model behavior on MC20.

**Result:** MIXED. Mechanically `MATERIAL_EFFECT` per the pre-registered OR-rule (criterion i fired), but criterion ii (frozen-model behavior) showed no meaningful change, and criterion i's own VH result is an overshoot rather than a convergence. A genuine, independently valuable finding emerged regardless: 43.8% of MC20's VH pixels are below the real sensor noise floor at this location.

**Effect on VV:** variance ratio 0.25 → 0.42 (partial improvement, still undershooting)
**Effect on VH:** variance ratio 0.70 → 3.80 (overshoot past 1.0, wrong direction for a clean "gap closed" story)
**Effect on NETRA output:** negligible — 3.05×10⁻⁶ → 5.11×10⁻⁶ (1.67×), still deep in the OOD-saturated regime

**Interpretation:** The NESZ-only hypothesis is **not sufficient on its own** to explain or fix MC20's OOD behavior, even though it produces a real, measurable, asymmetric effect on the underlying dB statistics. The frozen model does not care — its output magnitude is unchanged in any practical sense. This does not mean NETRA failed; it means this single, cheap correction is not the whole story, and the VH overshoot itself is a new question requiring investigation before treating "preprocessing" as understood.

**NEXT:**

    EXPERIMENT A — PREPROCESSING (narrowly scoped to the VH overshoot investigation, per the mechanical rule)

**DO NOT TRAIN. None performed. END.**
