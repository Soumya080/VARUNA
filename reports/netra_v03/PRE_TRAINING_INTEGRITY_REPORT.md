# NETRA v0.3 — Pre-Training Integrity Audit

**Date:** 2026-08-31. No training run. v0.2 checkpoint re-hashed identical;
v0.2 Gold, Part III, MC20, official test untouched.

---

## Executive Decision

# TRAINING_FORMULATION_REQUIRES_CHANGE

The pipeline **mechanics are correct and now proven** — but the
**experiment design is not yet capable of answering its own question**.
Two bugs were found and fixed; two scientific blockers remain and cannot
be fixed by code alone. Running the GPU job as originally specified would
burn hours and produce an uninterpretable — plausibly *misleading* —
result.

## Current Data

| Split | Tiles | Scenes | Wind |
|---|---|---|---|
| v0.3 train | 213 | 8 | 111 low / 106 medium |
| v0.3 val | 81 | 3 | 100% low |
| **CALM-GRD-HOLDOUT** | 215 | 8 | **100% low, 0/8 proximity-flagged** |
| v0.2 train (strong, read-only) | 34,992 | 2,187 | — |
| excluded | 91 | — | 77 proximity · 8 duplicate · 6 all-ignore |

## Label Semantics — verified on real samples

Weak batch measured directly from the loader: `ignore = 2.51%`,
`positive = 0.0000`, `negative = 97.49%`. Exactly the declared policy:
outside box → NEGATIVE, inside box → IGNORE, **never** inside → POSITIVE.

## Weak-Supervision Mechanics — EXECUTED, not inspected

Five mathematical tests, all passing
(`tests/unit/test_v03_weak_supervision_mechanics.py`):

1. Targets differing **only inside ignored pixels** ⇒ `loss(A) == loss(B)`
   to 1e-7. ✅
2. Flipping **one non-ignored** pixel ⇒ loss changes. ✅
3. Ignored pixels ⇒ **exactly zero** gradient; supervised pixels ⇒ nonzero. ✅
4. An **all-ignored** target ⇒ **NaN loss** (0/0 under mean reduction). ✅
   *This is how bug #1 below was found.*
5. `IGNORE_INDEX=255` does not collide with class ids `{0,1}`. ✅

## Bugs found and fixed

**Bug 1 — NaN-loss tiles (crash-level).** 6 tiles had box regions covering
~100% of the tile ⇒ all-ignore target ⇒ NaN loss ⇒ NaN propagates through
`backward()` and destroys **every** weight. Excluded via manifest (files
retained, nothing deleted) and guarded by a regression test.

**Bug 2 — silent preprocessing mismatch.** v0.2 Gold stores tiles
**already normalized** to [0,1] (p2/p98, built-in); v0.3 stores **raw
Sigma0 dB** normalized at load with v0.3-train stats. Same physical
channel, very different transforms:

| physical VH | v0.2 range | v0.3 range |
|---|---|---|
| clip window | [−42.48, −13.83] (28.65 dB) | [−33.46, −20.05] (13.41 dB) |

| same dB | v0.2-norm | v0.3-norm | Δ |
|---|---|---|---|
| −33 | 0.331 | 0.034 | **0.296** |
| −20 | 0.784 | 1.000 | **0.216** |

Identical physics ⇒ inputs differing by up to **0.30** in [0,1], purely by
source. That hands the model a free domain shortcut. **Fixed:** v0.3 is
normalized with v0.2's frozen transform
(`normalization_v02_compat.json`), fit on v0.2 train only — no v0.3
val/holdout, Part III, or MC20 contribution.

## Physical Channel Contract — verified

v0.2's stat *named* "VV" has mean −32.1 dB and its "VH" −20.3 dB. VV must
be **brighter** than VH, so the name-"VV" channel is **physically VH** —
independently reconfirming the Smart-Fix band-order finding. Mapping was
therefore done **by physics, not by name**:

- v0.2 Gold: ch0 = VH, ch1 = VV
- v0.3 Gold: ch0 = VH, ch1 = VV → **match**, no compatibility layer needed
  for channel order.

## Strong-Positive Coverage

- Strong positive pixels: **1.299 × 10⁸**, **100% from Zenodo v0.2**.
- ESSD positive pixels: **0**, by policy and by source evidence.
- v0.2 train positive pixel fraction: 1.4162%; 17.3% of tiles contain oil.

Positive supervision is sufficient **in absolute terms** — but it is
entirely single-domain.

## ESSD Training Signal — the central finding

**Blocker B1 — domain exposure is negligible.** 213 ESSD tiles vs 34,992
Zenodo tiles = **0.62% of combined training pixels**. At this ratio the
"domain expansion" is a rounding error; the experiment cannot detect its
own independent variable.

**Blocker B2 — perfect domain/label confound.**

```
P(positive pixel | Zenodo tile) = 0.01416
P(positive pixel | ESSD   tile) = 0.00000   <- exactly zero, by construction
```

Domain predicts label availability perfectly. Gradient descent can reduce
loss by learning *"ESSD-looking input → background"*. MC20's documented
failure mode is **under-detection** in precisely this calm low-wind
domain — so the current formulation risks **reinforcing the very failure
the experiment exists to fix**. Domain exposure does not automatically
help; here the available supervision points the wrong way.

This is not a code defect. It follows from ESSD containing zero confirmed
positive pixels, which is a property of the source, established earlier
from its own `<segmented>0</segmented>` declaration.

## Option ranking (Phase 7)

| Option | Verdict |
|---|---|
| A: ESSD directly into segmentation loss | **Rejected** — this is B2; teaches "new domain = background" |
| B: ESSD as ignore-only domain exposure | **Rejected as specified** — mechanically sound but 0.62% of pixels (B1) and still carries B2's confound |
| **C: weak supervision with a valid positive constraint (MIL)** | **Recommended.** A box genuinely asserts *at least one* oil pixel inside — that is a true statement from the source, so a max-over-box positive constraint is **not fabrication**. It removes B2 by giving ESSD real positive signal without naming which pixels. Requires oversampling ESSD to a declared ratio to also address B1. |
| D: ESSD not used for training in run 1 | **Viable fallback.** Keep ESSD purely as the CALM-GRD-HOLDOUT evaluation domain. Costs nothing, risks nothing, answers less. |

## Class Balance

Pixel-level: v0.2 train 1.42% positive; v0.3 0% positive / 5.39% ignore /
94.61% negative. Tile-level v0.3: 79% oil-class. Scene-level: per-scene
cap already applied at P75 (36 tiles) with evenly-spaced deterministic
selection — no scene dominates, no positive duplication, no arbitrary
loss weights.

## Data Split / Leakage

Scene-level throughout, test-enforced (`test_no_scene_appears_in_two_splits`).
Exhaustive footprint check across **all 3,020** Zenodo Part I/II/III
tiles: holdout **0/8** flagged; train 6/8 and **val 3/3** flagged.
⇒ **Val is diagnostic only**; the holdout is the sole trustworthy
evaluation surface. Cross-split duplicates: 0. MC20 geographically
disjoint. Part III read-only.

**Consequence for early stopping:** disabled. Stopping on a
source-proximity-biased val would select for the *old* domain; stopping
on the holdout would contaminate it. Use a **fixed epoch budget**.

## Normalization

`netra-norm-v0.2-COMPAT-for-v0.3-mixed-pilot` — v0.2 train-only stats
applied to both sources. Val contribution 0, holdout 0, Part III 0,
MC20 0.

## CPU Smoke Test (real data, executed)

| batch | loss | finite | grad norm | NaN grads |
|---|---|---|---|---|
| STRONG (4 v0.2 tiles) | 0.95877 | ✅ | 3.70 | none |
| WEAK (4 v0.3 tiles) | 0.93756 | ✅ | 3.75 | none |
| MIXED (2+2) | 0.90098 | ✅ | 3.88 | none |

Shapes `(4,2,512,512) → (4,2,512,512)`. Checkpoint re-hashed **unchanged**.

## Tiny Overfit Control

1 strong tile, 30 steps: loss **0.457 → 0.018**, monotonically decreasing.
Model + loss + labels can learn when the problem is trivial ⇒ no latent
defect in the learning path.

## Reproducibility

Config enumerates every required field (git commit, both manifest hashes,
normalization version + hash, seed, library/CUDA/GPU versions, all
hyperparameters, and the label-quality distribution actually seen by the
loss). Run is rerunnable from the config alone.

## Training Risks

1. Non-finite loss from an unforeseen all-ignore batch — guarded
   (skip-and-log) in addition to the manifest exclusion.
2. Weak data silently dominating or vanishing — mitigated by logging the
   per-batch strong/weak/ignore/positive/negative counts.
3. Selecting on a biased val — mitigated by disabling early stopping.
4. Holdout contamination — mitigated by policy and by it never being
   loaded during training.

## Second-Source Need

**A — stronger pixel-level masks**, decisively over geographic diversity.
B2 exists because ESSD has zero positive pixels; more geography with the
same weak labels would reproduce the confound at larger scale. Geographic
diversity remains desirable but is second-order.
Spec already written: `docs/datasets/NETRA_V03_SECOND_SOURCE_REQUIREMENTS.md`.

## Exact Next Action

1. **Choose Option C or D** (recommend C; D if GPU time is scarce).
2. If C: implement the MIL positive constraint + declare an ESSD
   oversampling ratio; re-run this audit's Phase 4/5 proofs against the
   new loss.
3. Write `scripts/netra_v03/07_train_v03_pilot.py` (does not exist yet).
4. Only then launch on a GPU host — this machine has none
   (`torch.cuda.is_available() == False`).

## Safety

deleted=0 · moved=0 · renamed=0 · overwritten=0 · v0.2 checkpoint
sha256 `9f38c690…2cd66` unchanged · v0.2 Gold, Part III, MC20, official
test untouched. Tests: **46 passing**.
