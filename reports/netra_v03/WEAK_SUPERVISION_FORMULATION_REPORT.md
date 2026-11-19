# NETRA v0.3 — Weak-Supervision Formulation Resolution

**Date:** 2026-08-31. No full training run. v0.2 checkpoint re-hashed
identical; v0.2 Gold, Part III, MC20, CALM-GRD-HOLDOUT untouched.

---

## Decision

# MIL_VALID_AND_PILOT_READY

- **Loss:** `L_total = 1.0·L_strong + 1.0·L_weak_negative + 1.0·L_MIL`,
  with `L_MIL = −log(topk_mean(p_oil inside box))`, `ignore_index=255`.
- **Pooling:** **top-k mean**, `k = max(16, 0.10·|B|)`.
- **Weak sampling ratio:** **10%**.
- **Budget:** **fixed 30 epochs**, early stopping disabled, `grad_clip=5.0`.

---

## Hardware correction (important)

Earlier reports in this investigation stated "no GPU on this machine."
**That was wrong.** It was measured against the system Python instead of
`./.venv`. Measured in the project venv:

```
torch.cuda.is_available() = True
NVIDIA GeForce RTX 3060, 12.88 GB VRAM
```

Measured peak VRAM for this config at batch_size 8: **2.00 GB** — ample
headroom. The pilot can run on this machine.

## The blocker being resolved

`P(positive pixel | ESSD) = 0` while `P(positive pixel | Zenodo) = 0.01416`,
with ESSD at 0.62% of pixels. Under the previous ignore-only plan the loss
was minimisable by learning *"ESSD-looking domain → background"* — the
opposite of the goal, and aligned with MC20's actual under-detection
failure.

## Candidate MIL formulations — chosen by measurement

Real box sizes span **144 → 248,320 px (1,700×)**, which is what
discriminates the candidates. Synthetic controlled cases, scores for
`[pure noise / one hot pixel / real 5% object]`:

| pooling | N=144 | N=3,200 | N=27,019 | N=248,320 | verdict |
|---|---|---|---|---|---|
| hard max | 0.100/**0.990**/0.900 | same | same | same | **Rejected** — one pathological pixel (0.990) scores *higher* than a genuine object (0.900) |
| LSE (r=1) | 5.02/5.03/5.09 | 8.12/8.12/8.19 | 10.26/10.26/10.32 | 12.47/12.47/12.54 | **Rejected** — grows with box size; noise vs object differ by 0.06 |
| noisy-OR | **0.999**/1.000/1.000 | 1.000/1.000/1.000 | 1.000/1.000/1.000 | 1.000/1.000/1.000 | **Rejected** — saturates to ~1 on **pure noise** at every size |
| gmean (r=8) | 0.075/0.532/0.617 | 0.076/0.361/0.619 | 0.076/0.276/0.619 | 0.076/0.210/0.619 | viable but size-dependent, one-hot leakage at small N |
| **top-k (10%)** | 0.091/0.147/0.447 | 0.095/**0.098**/0.499 | 0.095/0.095/0.499 | 0.095/0.095/0.499 | **SELECTED** |

**top-k** makes a single hot pixel *indistinguishable from noise*
(0.095 vs 0.095) while a real object scores ~5× higher, and is stable
across a 1,700× size range.

## Mathematical justification

The annotation asserts *"an oil **object** exists inside this box."* An
object occupies many contiguous pixels. So requiring the top **k** pixels
— not the single max — is **more faithful to the annotation**, not a
convenience. It never asserts *which* pixels are oil; the model chooses
them.

## Gradient / mathematical tests (Phase 4 + 16) — all executed

15 deterministic tests in `tests/unit/test_v03_mil_loss.py`, all passing:

1. All-low-probability box → high MIL loss (>4.0) ✅
2. Object-sized positive region in box → MIL loss falls ✅
3. Pixels **outside** the box do not change the MIL term (1e-7) ✅
4. MIL yields positive-learning gradient **inside** the box, and exactly
   zero outside it ✅
5. Location-invariance: two boxes with oil in different places give
   identical MIL ✅ (proves no location knowledge is required)
6. No NaN and finite gradients across logits −20…+20 ✅
7. Empty box fails safely (`n_boxes=0`, MIL=0, finite) ✅
8. All-ignore weak sample does not NaN ✅
9. Isolated hot pixel cannot capture most of the achievable MIL
   reduction ✅
10. Tiny / huge / boundary-touching boxes all finite ✅
11. `topk_pool` stable across box sizes (<0.15 spread) ✅
12. Strong and weak terms computed on disjoint samples ✅

*(One test initially failed — my assertion, not the loss: I backwarded
`total` instead of `mil`, so the weak-negative CE's legitimate
outside-box gradient tripped it. Corrected to backward the MIL term.)*

## Does MIL actually solve B2? (Phase 5) — measured on real data

| sample | L_strong | L_weak_neg | L_MIL | gradient on OIL logit |
|---|---|---|---|---|
| ESSD **weak oil box** | 0.0000 | 0.9482 | **0.1744** | **−1.22e−05 in-box, on exactly 10% of box pixels** → pushes oil probability **UP** |
| ESSD negative/lookalike | 0.0000 | 0.9468 | 0.0000 | +2.09e−06 → pushes oil **DOWN** (correct) |
| Zenodo strong positive | 0.9607 | 0.0000 | 0.0000 | **100%** of true-positive pixels get negative gradient (correct) |

**B2 is eliminated.** ESSD now contributes *both* positive (MIL, inside
boxes) and negative (outside boxes) signal. Domain no longer predicts
"background only." The 10.0% matches `topk_frac` exactly — the gradient
goes precisely to the top-k pixels, as designed.

## Weak/strong gradient comparison

Grad norms by batch type (untrained model, real data): strong-only
**3.71**, weak-only **18.63**, mixed **12.86**. Finite and stable, but
asymmetric — the `−log(topk)` gradient concentrates on few pixels.
Mitigated with a conservative `grad_clip_norm = 5.0` (a guard, not a
tuned value).

## Sampling-ratio analysis (Phase 6) — measured, not preferred

At batch_size 8 over one pass of the 34,992 strong tiles:

| ratio | weak/batch | weak re-shown per strong epoch | verdict |
|---|---|---|---|
| 5% | 0.4 | 8.6× | most batches contain **no** weak sample |
| **10%** | **0.8** | **18.3×** | **selected** |
| 20% | 1.6 | 41.1× | heavy repetition of 213 tiles / 8 scenes |
| 25% | 2.0 | 54.8× | memorization risk |

10% is the **smallest** ratio that makes the domain visibly present
without letting 213 weak tiles from 8 scenes be re-shown 40–55× per
epoch. Sampling is deterministic and index-based — **no file duplication**.

## Loss decomposition / weighting (Phase 7)

Measured raw magnitudes on real data, untrained model:
`L_strong = 0.9385`, `L_weak_negative = 0.9460`, `L_MIL = 0.2032`
(MIL/strong = **0.22**). All three are the same order, so **unit weights**
give comparable gradient influence. **No weight was tuned**, and none was
selected using MC20, Part III, or the holdout.

## Batch audit (Phase 13), on CUDA

| batch | strong | weak | boxes | pos px | ignore px | neg px | L_str | L_wneg | L_MIL | L_tot | grad |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A strong-only | 4 | 0 | 0 | 19,664 | 0 | 1,028,912 | 0.9599 | 0.0000 | 0.0000 | 0.9599 | 3.71 |
| B weak-only | 0 | 4 | 3 | 0 | 23,200 | 1,025,376 | 0.0000 | 0.9372 | 0.2259 | 1.1631 | 18.63 |
| C mixed | 3 | 1 | 1 | 14,008 | 12,876 | 1,021,692 | 0.9124 | 0.9298 | 0.1751 | 2.0173 | 12.86 |

All finite, no NaN gradients, optimizer stepped. Weak samples contribute
**zero** positive pixels — as they must — with the positive signal
arriving via MIL instead.

## CPU + CUDA smoke (Phase 14)

The real `07_train_v03_pilot.py` was executed end-to-end (6 steps, CPU),
and the batch audit ran on CUDA. Loader → model → forward → MIL +
segmentation loss → backward → optimizer step: all finite, ignored pixels
stay ignored, checkpoint hash unchanged.

## Overfit controls (Phase 15)

- **Control A** (strong tile): loss 0.457 → 0.018. ✅
- **Control B/C** (weak box, **no** pixel location given to the loss):
  `L_MIL 0.0866 → 0.0000`, and afterwards
  - mean `p_oil` on the **true** dark object: **0.9996**
  - mean `p_oil` elsewhere inside the box: 0.7489
  - mean `p_oil` outside the box: **0.0104**

  **MIL located the object without ever being told where it was**, and did
  not force the whole box positive — exactly existence-only semantics.

## Second-source requirement (Phase 18)

**Still stronger pixel-level masks**, and the pilot **can proceed without
them**. MIL converts ESSD from harmful to useful, but positive *pixel*
supervision still comes solely from Zenodo. Broader geography with the
same weak labels would not close that gap. Spec:
`docs/datasets/NETRA_V03_SECOND_SOURCE_REQUIREMENTS.md`.

## Remaining scientific risk

1. Only **8 weak scenes / 213 tiles** — the domain sample is narrow; a
   null result may reflect sample size, not the hypothesis.
2. `topk_frac = 0.10` is a declared modeling assumption about what
   fraction of a box is oil. Measured median in-box "plausibly oil" is
   ~37.7%, so 10% is deliberately conservative — but it is an assumption,
   not a source fact.
3. Val is proximity-contaminated ⇒ fixed budget only; no "best val" model
   may be claimed.
4. Weak-batch gradient asymmetry (5×) is clipped, not eliminated.
5. This is a **pilot**: it tests domain exposure, and cannot by itself
   establish accuracy improvement.

## Safety

deleted=0 · moved=0 · renamed=0 · overwritten=0 · v0.2 checkpoint
`9f38c690…2cd66` unchanged · v0.2 Gold, Part III, MC20, CALM-GRD-HOLDOUT
untouched. Tests: **32 passing** across loader, ignore-mechanics, and MIL.
