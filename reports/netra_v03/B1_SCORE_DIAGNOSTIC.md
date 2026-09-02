# B1 PR-Curve / Score-Distribution Diagnostic

**Date:** 2026-09-01. **Diagnostic only.** No training, no model
modification, no threshold selected or deployed. v0.2 checkpoint, B1
checkpoint, and the CALM-GRD-HOLDOUT dataset all verified unchanged
before and after.

## Question

Did B1 genuinely lose its ability to rank oil vs background, or did it
mainly shift/suppress its score distribution so the frozen v0.2
threshold (0.806) became inappropriate?

## Data / artifacts used

No stored per-pixel score arrays existed anywhere in the repository —
`scripts/netra_v03/08_b1_final_evaluation.py` computed a 1024-bin
PR-histogram in-memory but persisted only derived scalars (PR-AUC,
best-F1, max-probability) to JSON, and B1's own full holdout evaluation
took 15.13s, confirming a rerun is cheap. A **new, read-only,
forward-pass-only** script (`scripts/netra_v03/09_b1_score_diagnostic.py`)
was written to reproduce and save the full histograms this diagnostic
needs. No backward pass, no optimizer, no training occurred.

**Integrity checks performed before running:**
- B1 checkpoint sha256 `3b76c589ac2206…f6f8e12dd` — verified against the
  hash recorded in `NETRA_V03_B1_FINAL_EVALUATION.md`, matched exactly.
- v0.2 checkpoint sha256 `9f38c690d0ef16…f242f1d2e2cd66` — matched exactly.
- CALM-GRD-HOLDOUT: 215 tiles / 8 scenes, `label_quality={WEAK_BOX}` —
  matched the final evaluation report's `n_tiles: 215`.
- Evaluation used `apply_ignore=False`, exactly matching
  `08_b1_final_evaluation.py`'s own convention (box interior = target 1,
  the only available ground-truth proxy for scoring — distinct from the
  ignore-based training-time semantics used in the MIL loss itself).
- **Cross-check:** the histogram-derived PR-AUC reproduced the original
  report's scalar values essentially exactly — v0.2 **0.3928** vs
  0.3928 previously recorded; B1 **0.3775** vs 0.3775 previously
  recorded. This confirms the new diagnostic is measuring the same
  quantity as the frozen evaluation, not a different or inconsistent one.

Both checkpoints re-hashed **unchanged** after the run. Raw histograms
saved to `artifacts/experiments/netra_v03/pilot_01_run2/score_diagnostic/`
for any future reuse (so this rerun need not be repeated).

## Score distributions

| | v0.2 positive-region | v0.2 negative-region | B1 positive-region | B1 negative-region |
|---|---|---|---|---|
| n pixels | 2,813,291 | 53,547,669 | 2,813,291 | 53,547,669 |
| median (p50) | 0.000 | 0.000 | 0.000 | 0.000 |
| p90 | **0.913** | 0.000 | **0.000** | 0.000 |
| p95 | **0.968** | 0.000 | **0.000** | 0.000 |
| p99 | 0.991 | 0.034 | 0.999 | 0.000 |

"Positive-region" pixels are inside a real annotation box (the ~62.3%
non-oil-interior caveat from the label-noise analysis applies equally to
both models' evaluation here — this is a property of the ground truth,
not of either model).

**The critical difference is not p99, it's p90/p95.** v0.2's positive-region
pixels are already solidly above the 0.806 threshold at the 90th
percentile (0.913); B1's positive-region pixels are still at **exactly
0.000** at the 90th and 95th percentile — meaning **90%+ of true
positive pixels get essentially the same score as background**, with
only the top ~1–5% of positive pixels retaining an elevated score.

## PR curve / best-achievable performance

| | v0.2 | B1 |
|---|---|---|
| PR-AUC (histogram, cross-checked) | 0.3928 | 0.3775 |
| Best-F1 achievable at **any** threshold | **0.408** | **0.095** |
| Threshold achieving that best F1 | 0.00098 | 0.000 |

**This is the decisive number.** If B1's problem were purely that its
scores are shifted/compressed below 0.806 while otherwise well-separated
(calibration), then B1's *best-achievable* F1 — searching over every
possible threshold, not just 0.806 — should be close to v0.2's
best-achievable F1. It is not: **0.095 vs 0.408, a >4× gap**, even under
the most generous possible re-threshold. No single global threshold
recovers v0.2-level performance from B1's scores, because the underlying
signal for most positive pixels was never there to threshold into.

(Aside, noted but not acted on: v0.2's own best-F1 threshold on this
specific WEAK_BOX evaluation surface is 0.00098, far below the frozen
0.806 — a real property of this evaluation surface for both models, not
a B1-specific finding. Reported for completeness; **not** used to select
or recommend a deployment threshold here.)

## Threshold sweep (observational only)

| Threshold | v0.2 foreground fraction | B1 foreground fraction |
|---|---|---|
| ~0.025 | 0.02407 | 0.00159 |
| ~0.05 | 0.02085 | 0.00152 |
| ~0.2 | 0.01604 | 0.00139 |
| ~0.6 | 0.01167 | 0.00127 |
| 0.806 (frozen) | 0.00936 | 0.00122 |
| ~1.0 | 0.00000 | 0.00039 |

**Even at the most permissive threshold tested (~0.025), B1's
foreground fraction (0.00159) is still ~15× lower than v0.2's foreground
fraction at the same low threshold (0.02407)**, and lower than v0.2's
foreground fraction *at its much higher default threshold* (0.00936 at
0.806). Lowering B1's threshold does not approach v0.2's activation
level at any point on the curve. This directly rules out "B1 just needs
a lower threshold" as a sufficient explanation.

## Spatial score diagnostic

10 deterministic real oil-class holdout tiles (first 10 by sorted
tile_id), same tiles for both models, no labels created or altered:

| | v0.2 | B1 |
|---|---|---|
| Tiles with **zero** predicted foreground @ 0.806 | 3/10 | **10/10** |
| Mean true-oil-region score | 0.1429 | **0.0052** |
| Mean max score in tile | 0.6656 | **0.1914** |

**Every single sampled real-oil tile produced zero predicted foreground
from B1 at the frozen threshold** — v0.2, while itself imperfect (3/10
misses, consistent with its own known limitations on this weak-box
evaluation surface), still activates on the majority of the same tiles.

## Interpretation

**A. Ranking capability, partially preserved:** B1's PR-AUC (0.3775) is
only 3.9% below v0.2's (0.3928) — B1 still, in aggregate across the
whole holdout, ranks *some* of its highest-confidence pixels above the
general negative-pixel population. This is why AUC alone looked
reassuring in the original evaluation.

**B. But the representation for the bulk of positive pixels has
degraded, not just shifted:** 90%+ of true positive pixels score at
essentially the same level as background (p90=p95=0.000), the
best-achievable F1 at any threshold is >4× worse than v0.2, the
threshold sweep shows no recovery at any point on the curve, and 10/10
spatially-sampled real-oil tiles show zero activation. A pure
shift/compression (calibration) failure would preserve strong
positive/negative separation and only require a lower cutoff to recover
comparable recall — that is not what is observed.

## Classification

# MIXED — leaning strongly REPRESENTATION_DOMINANT

Not `CALIBRATION_DOMINANT`: the threshold sweep and best-achievable-F1
comparison directly rule out "just needs a lower threshold" as
sufficient. Not `INCONCLUSIVE`: the evidence is consistent and
directional across every measurement (percentiles, PR curve, threshold
sweep, spatial diagnostic). Not purely `REPRESENTATION_DOMINANT` either,
because AUC is only mildly reduced — B1 has not lost *all* discriminative
signal, only the ability to express it broadly across most positive
pixels; it retains a narrow, very-high-confidence sliver (consistent
with, though not proof of, the "minimal confident core" mechanism
flagged as a plausible cause in the master report's failure analysis).

## Limitations

- This diagnostic uses the same `WEAK_BOX`-as-ground-truth evaluation
  convention as the original B1 evaluation (box interior = target 1);
  it inherits that convention's own caveats (§ label-noise analysis,
  ~62.3% non-oil interior) equally for both models, so it cannot
  separate "true recall loss" from "recall loss against noisy labels" —
  only the **relative** B1-vs-v0.2 comparison on identical labels is
  used, which is valid regardless of label noise.
- The spatial sample is 10 tiles, deterministic but small; used as an
  illustrative cross-check of the aggregate histogram finding, not as an
  independent statistical claim.
- This diagnostic does **not** identify *why* the representation
  degraded (MIL weighting, top-k fraction, sampling ratio, or domain
  shift remain live, non-exclusive hypotheses per the master report's
  §12 — this diagnostic narrows *what kind* of failure occurred, not
  its root cause).

## Next recommendation

Per the governing task's decision logic: this result is **MIXED**, so
the single most informative next experiment is identified rather than
launched. Given the "minimal confident core" signature (sharp p99 spike,
flat p90/p95, 4× best-F1 gap) most directly implicates the MIL
formulation's `topk_frac=0.10` and unit loss weighting as the most
proximate, cheapest-to-test candidate — **a topk_frac / MIL-weight
ablation** (§17 option 2 of the master report) is the most informative
next step, over jumping straight to new-data acquisition or domain
adaptation, both of which are more expensive and do not have direct
evidence pointing at them from this diagnostic specifically. This is a
recommendation, not an action — no ablation was run in this task.

## Safety

deleted=0 · moved=0 · renamed=0 · overwritten=0 · v0.2 checkpoint
unchanged (re-hashed) · B1 checkpoint unchanged (re-hashed) ·
CALM-GRD-HOLDOUT untouched (read-only dataset access) · no threshold
selected, deployed, or written into any config · no training, no
long-running compute (total GPU time ≈11 s for both models combined).
