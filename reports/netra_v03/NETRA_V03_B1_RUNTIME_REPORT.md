# NETRA v0.3-B1 — Runtime / Pre-Flight Report

**Date:** 2026-08-31. Training **LAUNCHED and RUNNING**. Evaluation
(Phases 14–21) pending run completion — **no results are claimed here.**

## Phase 0 — Worktree / concurrency

No competing NETRA/Python training process. GPU held only by desktop
applications (1,231 MiB). Nothing killed, overwritten, or modified.

## Phase 1 — Hardware / environment (project venv only)

| item | value |
|---|---|
| OS | Windows-11-10.0.26200 |
| Python | 3.12.14 (`./.venv/Scripts/python.exe`) |
| PyTorch / torchvision | 2.6.0+cu124 / 0.21.0+cu124 |
| CUDA / cuDNN | 12.4 / 9.1.0 |
| GPU | **NVIDIA GeForce RTX 3060**, capability 8.6, 28 SMs |
| VRAM | 12.88 GB total, **11.79 GB free** at launch |
| Driver | 591.86 |
| CPU | Intel64 F6 M151 S2 — 12 physical / 20 logical cores |
| RAM | 34.19 GB total, 18.57 GB available |
| Disk | 2,000 GB total, **1,022.7 GB free** |

Saved: `artifacts/experiments/netra_v03/pilot_01/hardware_profile.json`.

## Phase 2 — Resource safety

Measured peak VRAM **3.80 GB** of 12.88 → ~9 GB headroom. RAM and disk
margins large. Safe for a 30-epoch run.

## Phase 3 — Configuration verified

resnet34 U-Net, in_ch 2, classes 2 · loss = CE(strong) + CE(weak-neg) +
`−log(topk_mean)` MIL, weights (1.0, 1.0, 1.0) · topk_frac 0.10,
topk_min 16, ignore_index 255 · ESSD ratio 10% · AdamW lr 1e-4 ·
batch 8 · grad clip 5.0 · **30 epochs, early stopping DISABLED** ·
seed 42 · normalization `netra-norm-v0.2-COMPAT-for-v0.3-mixed-pilot` ·
checkpoints → `artifacts/experiments/netra_v03/pilot_01/`.

## Phase 4 — Data integrity pre-flight

| check | result |
|---|---|
| strong manifest sha256 | `89d3cf69d7131964…` |
| weak records sha256 | `2b95536895868caf…` |
| normalization sha256 | `290421906a1b295b…` |
| strong train tiles | 34,992 |
| weak train tiles | 213 (175 oil-box, 38 negative) |
| holdout tiles | 215 — **excluded from training** |
| holdout split via loader | **REFUSED** ✅ |
| Part III / MC20 / holdout paths | **REFUSED** ✅ |
| sample sanity | img (2,512,512) f32 in [0,1], target (512,512) i64 |

## Phase 5 — Real timed smoke test (CUDA)

| stage | mean seconds |
|---|---|
| batch load | 0.2903 (**51% of step — I/O bound**) |
| forward | 0.0820 |
| loss | 0.0095 |
| backward | 0.1783 |
| optimizer | 0.0077 |
| **total / step** | **0.5681 ± 0.2208** |

Throughput 14.08 samples/s · peak VRAM 3.80 GB · **140/140 weight
tensors changed** · finite loss & gradients every step · no NaN/Inf ·
weak batches produced boxes (`n_boxes = 1`) with a non-zero MIL term ·
v0.2 checkpoint hash unchanged.

**Observation (recorded, not acted on):** pre-clip gradient norms on
mixed batches ran **9.9–82.8** against the configured clip of **5.0**, so
most steps are clipped, uniformly scaling the effective step size. The
clip was fixed *before* this observation and was **not** retuned —
changing it now would be tuning on the run. Flagged for interpretation at
evaluation time.

## Phase 6 — Runtime estimate (from measured throughput)

```
steps/epoch:              4,998   (7 strong + weak at 10%, batch 8)
measured seconds/step:    0.5681 ± 0.2208
estimated minutes/epoch:  47.3
estimated 30-epoch time:  23.73 h   (range 14.53 – 32.93 h)
expected completion:      2026-09-01T16:38 (local)
```
Saved: `artifacts/experiments/netra_v03/pilot_01/runtime_estimate.json`.

## Phase 7 — Smoke gate: ALL PASSED

CUDA ✅ · correct GPU ✅ · VRAM ✅ · RAM ✅ · disk ✅ · manifests ✅ ·
normalization ✅ · channel order ✅ · MIL formulation ✅ · strong data ✅ ·
weak data ✅ · holdout excluded ✅ · Part III excluded ✅ · MC20 excluded ✅ ·
finite forward ✅ · finite backward ✅ · finite optimizer step ✅ ·
MIL positive-learning gradient ✅ · no v0.2 mutation ✅ · smoke completed ✅ ·
runtime estimate reasonable ✅

## Phase 8 — Launch

```
./.venv/Scripts/python.exe scripts/netra_v03/07_train_v03_pilot.py \
  --config configs/lab/netra_v03_domain_expansion.yaml \
  --out artifacts/experiments/netra_v03/pilot_01/
```
git commit `2c87e4f` · seed 42 · hashes as above.

## Phase 9 / 10 — Monitoring

`scripts/netra_v03/monitor_b1.py` appends to
`artifacts/experiments/netra_v03/pilot_01/monitor.jsonl` and prints the
status panel; **ETA is recomputed from measured throughput at every
poll**, never held fixed. A session monitor polls every 20 min and also
watches for `Traceback | Error | out of memory | Killed | assert` and for
process disappearance.

**First observed status (260 steps in):** GPU 99% during compute, VRAM
5,352 MiB, loss_total 0.9429 → 0.1232, grad_norm 1.31, NaN-guard trips 0,
process RUNNING, ETA 22.96 h. Measured 0.543 s/step — consistent with the
estimate.

## Status

**Training in progress.** Phases 13–21 (completion, CALM-GRD-HOLDOUT
evaluation, v0.2 comparison, MC20 / Part III external reporting, success
determination) require the run to finish and are **not** reported here.
**No NETRA_STATUS is asserted yet** — asserting one now would be
inventing a result.

## Safety

deleted=0 · moved=0 · renamed=0 · overwritten=0 · v0.2 checkpoint
`9f38c690…2cd66` unchanged (hash recorded pre-launch) · v0.2 Gold,
Part III, MC20, CALM-GRD-HOLDOUT untouched.
