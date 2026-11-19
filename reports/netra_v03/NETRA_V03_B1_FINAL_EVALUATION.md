# NETRA v0.3-B1 FINAL SCIENTIFIC EVALUATION

**Date:** 2026-09-01  
**Experiment:** `pilot_01_run2` (Domain Expansion Pilot)  
**Evaluator:** Automated E2E Pipeline (Session Takeover)

## 1. Executive Verdict

> [!WARNING]
> **VERDICT: `V03_B1_REGRESSION`**
>
> The NETRA v0.3-B1 model demonstrates a severe performance degradation on the primary target domain (CALM-GRD-HOLDOUT) compared to the frozen v0.2 baseline. While training loss converged smoothly, the model learned a more conservative representation that depressed recall by a factor of 6.6x and IoU by a factor of 6.2x relative to v0.2. B1 will NOT be deployed.

**Primary Finding:** The MIL weak-supervision domain expansion pilot converged successfully but failed to generalize. Instead of learning to detect low-wind oil, it became exceptionally timid, reducing both false positives and true positives drastically.

**Biggest Limitation:** Bounding box labels (WEAK_BOX) fundamentally cap IoU at ~0.38. However, even accounting for this ceiling, v0.2 vastly outperforms B1 on the exact same holdout data.

**Next Exact Action:** Perform failure analysis on the MIL weak-supervision formulation. Diagnose whether the 10% sampling ratio or the specific MIL loss weighting caused the collapse in recall. Do NOT advance to integration.

---

## 2. Exact Checkpoint

| Field | Value |
|---|---|
| **Path** | `artifacts/experiments/netra_v03/pilot_01_run2/last.pt` |
| **SHA256** | `3b76c589ac220687c78e5db38be171294657ec6819413fd9af32221f6f8e12dd` |
| **Size** | 293,460,420 bytes |
| **Status** | IMMUTABLE / LOCKED |

---

## 3. Training Summary & Hardware

*   **Epochs:** 30/30 (Fixed, early stopping disabled)
*   **Total Runtime:** 59,219 seconds (≈16.4 hours)
*   **Hardware:** 1x NVIDIA GeForce RTX 3060 (12.88 GB)
*   **Final Loss (window avg):** 0.015973 (down from 0.9429)
*   **Assessment:** Optimization was **BENIGN**. The model did not crash, loss decreased smoothly, and gradient clipping only engaged on 1.2% of batches. The failure is representational, not numerical.

---

## 4. CALM-GRD-HOLDOUT Results (PRIMARY TEST)

**Dataset:** 215 tiles across 8 valid low-wind scenes. (14 scenes total in holdout split, 8 containing oil tiles).
**Threshold:** 0.806 (Frozen v0.2 standard, not retuned).

| Metric | v0.3-B1 | v0.2 Baseline | Relative Change |
|---|---|---|---|
| **IoU (oil)** | `0.0199` | `0.1254` | **-84.1%** |
| **Dice / F1** | `0.0390` | `0.2229` | **-82.5%** |
| **Precision** | `0.8238` | `0.7117` | +15.7% |
| **Recall** | `0.0200` | `0.1321` | **-84.8%** |
| **PR-AUC** | `0.3775` | `0.3928` | -3.9% |
| **Foreground Frac** | `0.0012` | `0.0092` | -86.9% |

> [!CAUTION]
> Direct comparison of these raw IoU numbers with the v0.2 official test (IoU 0.6458) is **NOT_DIRECTLY_COMPARABLE**. The official test used `STRONG_PIXEL` labels. This holdout uses `WEAK_BOX` labels containing ~62% background pixels inside the positive mask.
>
> However, comparing B1 vs v0.2 **ON THIS EXACT SAME HOLDOUT** is perfectly valid, and shows a catastrophic drop in recall.

### Per-Scene IoU Breakout (v0.3-B1)

*   `..._20190716T154816_...`: IoU = 0.0897 (Best)
*   `..._20191001T155619_...`: IoU = 0.0272
*   `..._20190404T155610_...`: IoU = 0.0178
*   `..._20190610T154813_...`: IoU = 0.0130
*   `..._20190306T154810_...`: IoU = 0.0093
*   `..._20191130T155618_...`: IoU = 0.0011 (Worst)
*   *Mean Scene IoU: 0.0263* (vs v0.2 Mean: 0.1190)

---

## 5. Domain Behavior Analysis

### Low-Wind Regime
The entire CALM-GRD-HOLDOUT test set is strictly low-wind (<5m/s). B1 achieved only 0.0200 recall here. The domain expansion failed to impart meaningful low-wind detection capability.

### Negative / Lookalike
B1 produced an extremely low False Positive rate (`0.000225`), actually improving upon v0.2 (`0.002812`). However, this was achieved via a global collapse in foreground prediction (Foreground fraction dropped from ~1% to ~0.1%). It did not learn to distinguish lookalikes better; it just stopped predicting oil entirely.

### Source Domain & MC20 External
Given the catastrophic failure on the primary target domain (Regression), further processing of MC20 external data and Zenodo Part III source preservation is unnecessary to determine the final verdict. The model is already disqualified from deployment.

---

## 6. Scientific Interpretation

The MIL (Multiple Instance Learning) weak-supervision domain expansion pilot succeeded as an engineering exercise but failed as a scientific intervention.

By enforcing `-log(topk_mean)` on the weak boxes alongside strong pixelwise loss, the model learned that the safest way to minimize loss across the mixed domain was to become extremely conservative. It maintained high precision (0.82) by only activating on the absolute highest-confidence core pixels of oil slicks, abandoning the vast majority of the slick geometry (Recall 0.02).

This indicates that either:
1. The weighting of $L_{MIL}$ (1.0) was too low to force the network to activate broadly.
2. The `topk_frac` (0.10) was too restrictive, allowing the network to satisfy the MIL loss by predicting only a tiny sliver of oil inside the box.
3. The domain gap is too wide for simple mixed-batch weak supervision to bridge without explicit feature alignment.

---

## 7. Checkpoint Immutability Verification

| Artifact | Pre-Eval SHA256 | Post-Eval SHA256 | Status |
|---|---|---|---|
| B1 `last.pt` | `3b76c589...` | `3b76c589...` | ✅ UNCHANGED |
| v0.2 `best.pt` | `9f38c690...` | `9f38c690...` | ✅ UNCHANGED |

**Safety:** 0 files modified, 0 files deleted during this evaluation pass.
