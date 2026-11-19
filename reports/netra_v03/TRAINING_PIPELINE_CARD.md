# NETRA v0.3 Training Pipeline Card

**Audit status:** mechanics validated · formulation requires change.
Config: `configs/lab/netra_v03_domain_expansion.yaml` (marked NOT LAUNCHABLE).

## Data flow — every stage traced and verified

| Stage | Input | Output | dtype / shape | Semantics | Verified |
|---|---|---|---|---|---|
| source (strong) | Zenodo GeoTIFF | v0.2 Gold `.npy` | float32 (2,512,512) | **already normalized [0,1]** at build | ✅ |
| source (weak) | S1 SAFE measurement | v0.3 Gold `.npy` | float32 (2,512,512) | **raw Sigma0 dB**, NaN=nodata | ✅ |
| manifest | JSON records | tile list | — | membership; no globbing | ✅ |
| loader | records + split | tensors | float32 / int64 | deterministic sorted order | ✅ 12 tests |
| normalization | raw dB | [0,1] | float32 | v0.2 frozen transform, both sources | ✅ fixed |
| target assembly | mask + ignore | target | int64 | 0=NEG, 1=POS, 255=IGNORE | ✅ 5 tests |
| collate | samples | batch | (B,2,512,512)/(B,512,512) | — | ✅ |
| model | batch | logits | (B,2,512,512) | resnet34 UNet, frozen arch | ✅ |
| loss | logits+target | scalar | float32 | CE(ignore_index=255) | ✅ proven |
| backward | loss | grads | finite | ignored ⇒ zero grad | ✅ proven |
| optimizer | grads | weights | — | AdamW 1e-4 | ✅ step executed |

## Channel contract
`channel 0 = VH`, `channel 1 = VV` — **physically identical in both
sources**. v0.2's stat *named* "VV" is physically VH (mean −32.1 dB, the
darker channel); mapping is done by physics, never by name.

## Supervision contract
| Source | Positive px | Negative px | Ignored px |
|---|---|---|---|
| v0.2 Zenodo (STRONG_PIXEL) | 1.42% | rest | 0 |
| v0.3 ESSD (WEAK_BOX) | **0.00%** | 94.61% | 5.39% |

`label_quality` travels with every sample to the loss and is logged
per batch — it must never silently disappear.

## Evaluation contract
- **Primary:** CALM-GRD-HOLDOUT (215 tiles / 8 scenes / 100% low-wind /
  0 proximity-flagged). Never used for training, stopping, normalization,
  threshold, or model selection.
- **Diagnostic only:** v0.3 val — 3/3 scenes proximity-contaminated.
- **Never for tuning:** MC20, Zenodo Part III.
- **Early stopping DISABLED** — fixed epoch budget, because no
  uncontaminated selection signal exists.

## Guards in force
- all-ignore tiles excluded (would NaN) + regression test
- non-finite-loss batch guard (skip and log)
- per-batch strong/weak/ignore/pos/neg audit logging
- v0.2 checkpoint path never written by this pipeline

## Known blockers before launch
- **B1:** v0.3 is 0.62% of training pixels — domain exposure negligible.
- **B2:** P(positive|ESSD)=0 exactly ⇒ domain/label confound; risks
  teaching "new domain = background", the opposite of the goal.

## Monitoring (long GPU run)
Poll 10–20 min: epoch, step, train loss, grad norm, GPU util, VRAM, RAM,
disk, checkpoint age, process status, NaN-guard trips. On crash: preserve
logs + last valid checkpoint, record exact failure, resume only with an
identical config, never overwrite a valid best.
