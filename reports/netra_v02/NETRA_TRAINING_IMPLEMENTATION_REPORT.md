# VARUNA GRID v2 — NETRA TRAINING IMPLEMENTATION REPORT

**Generated:** 2026-08-29
**Scientific status: EXPERIMENTAL / UNVALIDATED** — a successful training run does not equal scientific validation.

---

## Repository

| | |
|---|---|
| Branch | `feat/netra-real-training` |
| Base commit | `5a0cd6733831c7703d4587ba43088fc04cb4d19b` |
| Working tree | Dirty — 23 changed/new paths, all additive. No deletions, no raw-data files touched, no force operations used. |
| Commit status | **Not yet committed** — held pending baseline completion, per instruction not to disturb anything until the run is confirmed stable. |

---

## Environment

| | |
|---|---|
| Python | 3.12.14 (`.venv/Scripts/python.exe` — verified project interpreter, not system python) |
| PyTorch | 2.6.0+cu124 |
| CUDA | 12.4, `torch.cuda.is_available() == True` |
| GPU | NVIDIA GeForce RTX 3060, 12.0 GB VRAM |
| RAM | 32 GB |
| Disk | D: ~1.1 TB free after Gold build (was 1.2 TB) |
| Caches | Redirected off the full C: drive to `D:\varuna_cache\{hf,torch,tmp}` — verified writable |

---

## Data

| Source | Scenes audited | QC failures | In training pool |
|---|---:|---:|---:|
| Zenodo Part I (oil positive) | 1,200 | 0 | 1,199 |
| Zenodo Part II — Lookalike (hard negative) | 685 | 4 (off-spec dimensions) | 681 |
| Zenodo Part II — No_Oil (hard negative) | 685 | 0 | 685 |
| **Total** | **2,570** | **4** | **2,565** |

---

## Dedup

Corrected policy: exact duplicate requires identical image bytes **and** identical mask bytes (SHA-256). Bounding-box overlap alone is not duplication.

| | |
|---|---|
| Exact pair duplicates | **1** — `zenodo_part1__00356` / `zenodo_part1__00357` |
| Same image / different mask | **1 group** — preserved (two annotations of one scene, not a duplicate) |
| Same mask / different image | **1 group of 1,366** — preserved (the negative all-zero masks; expected structure, not duplication) |

**Comparison:** v0.1's bbox-overlap rule discarded 826 of 1,200 Part I scenes based on footprint overlap alone, keeping only 374. The corrected content-hash rule keeps **1,199 of 1,200** — a 3.2× recovery of legitimate training data.

---

## Split

| | |
|---|---|
| Strategy | `geographic_region_stratified` — scene-level, computed before tiling |
| Grouping | Footprint-overlap connected components (594) → modal 5° geographic region (61 regions) → regions dealt to splits in stratified windows of ten |
| Train scenes | 2,187 (49 regions) |
| Val scenes | 226 (6 regions) |
| Test scenes | 152 (6 regions) |

**Geographic leakage:** **PASS**
- Scene identity across splits: PASS (0 shared scene IDs)
- Exact content duplication across splits: PASS (0 shared image+mask hash pairs)
- Footprint overlap across splits: PASS (0 overlap-components span a split boundary)
- Centroid proximity < 50 km: reported, not hidden — min inter-split distance 18.4–24.0 km, affecting 0.02–0.07% of cross-split scene pairs (expected at region boundaries; not resolved by merging regions, which would collapse the split)

**Temporal leakage:** **UNAVAILABLE** — no acquisition timestamps exist in either source. Never reported as PASS.

---

## Normalization

Computed on the **train split only** (2,187 scenes), frozen, applied verbatim to val and test. Valid-pixel rule: `finite AND NOT (VV == 0.0 AND VH == 0.0)`. 2.585% of pooled train pixels are nodata under this rule.

| Channel | v0.1 p2 | v0.1 p98 | **v0.2 p2** | **v0.2 p98** |
|---|---:|---:|---:|---:|
| VV | −42.55 dB | **0.00 dB** | −42.48 dB | **−13.83 dB** |
| VH | −27.47 dB | **0.00 dB** | −33.43 dB | **−7.52 dB** |

v0.1's p98 of exactly 0.00 dB was not a backscatter percentile — it was set by the ~2.6% of pixels that are exact zero-fill (land/border), landing inside the 98th-percentile bin. Excluding nodata fixes both the value and its instability (v0.1's statistic would flip discontinuously on any change in corpus composition).

- NoData excluded: **Yes**
- Train-only: **Yes**

---

## GOLD (NETRA-GOLD-v0.2)

| Split | Tiles |
|---|---:|
| Train | 34,992 |
| Val | 3,616 |
| Test | 2,432 |
| **Total** | **41,040** |

vs. v0.1's 5,984 tiles — **6.9× more** training data.

**Validation (Phase 15): PASS**
- 0 missing tiles of 41,040 manifested
- 0 failures across 8,961 deep-checked tiles (all positive tiles + 5% random sample)
- Value range observed: exactly [0.0, 1.0]
- Split agreement (disk vs. manifest): True
- Unmanifested stray files in Gold tree: 0

---

## DataLoader

| | |
|---|---|
| Manifest-driven | **Yes** — `NetraGoldDataset` reads `data/manifests/netra_gold_v0_2.json`; no directory glob exists anywhere in the training path |
| Real data | **Yes** |
| Synthetic fallback | **None.** `train_netra.py` exits with code 2 and prints a refusal message if the manifest is absent — it does not synthesize a replacement |

---

## Trainer

| | |
|---|---|
| Real optimizer | AdamW |
| Backward | Yes — real `loss.backward()`, gradient clipping, `scaler.step()` |
| AMP | Yes |
| Scheduler | Cosine decay with linear warmup |
| Checkpoint contents | `model_state_dict`, `optimizer_state_dict`, `scheduler_state_dict`, `scaler_state_dict`, `epoch`, `best_metric`, `config`, `dataset_version`, `manifest_hash`, `normalization_version`, `seed` |
| Resume | Yes — `train_netra.py --resume auto` loads `<experiment_id>_last.pt` |

---

## Evaluator

Real IoU / Dice / Precision / Recall / F1 / PR-AUC, computed from an exact streaming confusion matrix over model predictions — no hardcoded constants remain anywhere in the evaluation path.

**Sensitivity proof** (from the smoke test, section below): trained model, a freshly-initialized random model, and a model forced to predict all-OIL each produced **different** metric values, and none matched v0.1's hardcoded stub constants (0.75 / 0.80 / 0.82 / 0.92).

---

## CRITICAL 2-EPOCH REAL SMOKE TEST

**Hard gate — 200 real Gold tiles, 2 real epochs, real GPU. Executed once, result below.**

| Check | Result |
|---|---|
| Real 200 tiles loaded, verified on disk | **PASS** |
| 2 real epochs | **PASS** |
| Correct shapes `[B,2,512,512]` / `[B,512,512]` int64 | **PASS** |
| Loss measured (not a formula) | **PASS** — epoch 1: `0.775754`, epoch 2: `0.681911` (finite, epoch-varying) |
| Weights actually changed | **PASS** — parameter fingerprint `2ee9d4bd...` → `6f5403a9...` |
| Metrics are dynamic, not constants | **PASS** — trained (IoU 0.0360) ≠ fresh-random (IoU 0.0144) ≠ forced-all-OIL (IoU 0.0139); forced-all-OIL recall = 1.000000 exactly, as required; no value matches a v0.1 stub constant |
| GPU actually used | **PASS** — `cuda:0`, NVIDIA GeForce RTX 3060, 24.43M params |
| Peak VRAM | 3.29 GB |
| Checkpoint is real | **PASS** — 293.5 MB, all 11 required fields present |
| Checkpoint reload + inference | **PASS** — fresh model loads state dict, output shape `(8,2,512,512)`, all finite |

```
REAL_SMOKE_TEST:
  DATA               = PASS
  DATALOADER         = PASS
  GPU                = PASS
  FORWARD            = PASS
  LOSS               = PASS
  BACKWARD           = PASS
  WEIGHTS_CHANGED    = PASS
  METRICS_DYNAMIC    = PASS
  CHECKPOINT         = PASS
  RELOAD             = PASS

LONG_TRAINING_AUTHORIZED = TRUE
```

Evidence: `reports/netra_v02/06_smoke_test.json`, `reports/netra_v02/06_smoke_test.log`

---

## LONG TRAINING

| | |
|---|---|
| Authorized | **True** (all 10/10 smoke-test criteria passed) |
| Started | 2026-08-29 04:18:42 UTC |
| PID | 62408 — detached via PowerShell `Start-Process`, survives terminal closing |
| Epoch target | 50 |
| Batch size | 16 |
| AMP | On |
| Resume | Supported (`launch_baseline.ps1 -Resume`) |
| **Status at time of this report** | **COMPLETE** — early-stopped at epoch 40/50 (patience=8, no `iou_oil` improvement since epoch 32), 997.9 min total wall clock |

Only **one** baseline was launched — no sweep, no parallel experiments.

### Incidents during the run (both diagnosed, fixed, and re-verified before continuing)

1. **Epoch 15 (first attempt, PID 62408 launched 04:18:42 UTC):** Windows page-file exhaustion (`OpenBLAS error: Memory allocation still failed`), root-caused to orphaned worker processes never cleaned up after a crash, holding memory indefinitely. Killed the orphans, re-ran the real smoke test (10/10 PASS), resumed cleanly from the epoch-14 checkpoint.
2. **Epoch 15 (second attempt, PID 68804):** the fix applied for (1) — making train workers non-persistent so they respawn each epoch — introduced a *worse* failure: a native access-violation crash (`c0000005` in `c10.dll`, confirmed via Windows Event Log WER records) almost immediately after respawn. Reverted train workers to `persistent_workers=True` (the configuration proven stable for 14 real epochs pre-incident) and added a lighter mitigation instead: explicit `gc.collect()` + `torch.cuda.empty_cache()` at the train→val boundary each epoch. Re-verified via the real smoke test (10/10 PASS again), relaunched as PID 1496, resumed cleanly from epoch 14 a second time.
3. **No further incidents.** PID 1496 ran epochs 15 through 40 without interruption — 25 consecutive real epochs, VRAM flat at ~5.01 GB peak throughout, confirming the second fix actually held.

---

## Experiment

| | |
|---|---|
| Experiment ID | `netra_baseline_v02_dac482fcd84a` |
| Dataset version | `NETRA-GOLD-v0.2` |
| Manifest hash | `89d3cf69d7131964f30879506a6ec0cd07cf01a5900deef89a9c6c24697ff8c4` |
| Config hash | `dac482fcd84a` |
| Seed | 42 |

---

## Historical Invalid Runs

9 prior experiment records quarantined via `artifacts/experiments/INVALID.md` — **nothing deleted**, all files retained on disk for auditability:

- 3 NETRA records (`exp_2362388e`, `exp_36df6074`, `exp_490974d8`)
- 6 CHHAYA records (`exp_0878b2ee`, `exp_b2e985ea`, `exp_e9bf61be`, `exp_ef0b98d7`, `exp_93e1046e`, `exp_d8a628e5`)

All were produced by `SyntheticNetraDataset`/hardcoded-metric stubs against untrained, randomly-initialized checkpoints. `docs/datasets/NETRA_GOLD_V0_1.md` was similarly corrected in place (a caution notice prepended, original text preserved below it) rather than edited or removed.

---

## Final Results (val split, best checkpoint = epoch 32)

Computed from real predictions by `NetraEvaluator` — not hardcoded, not stub values.

| Metric | Value |
|---|---|
| IoU (oil) | **0.6149** |
| Dice / F1 (@thr=0.5) | 0.7616 |
| Precision (@thr=0.5) | 0.6834 |
| Recall (@thr=0.5) | 0.8598 |
| PR-AUC | 0.8424 |
| Best-F1 (calibrated) | 0.7885 @ **threshold=0.806** |

By source (val split):

| Source | Tiles | FP-pixel-rate | IoU (oil) |
|---|---|---|---|
| zenodo_part1 (real oil spills) | 1920 | 0.007012 | 0.6765 |
| zenodo_part2_lookalike (hard negative) | 688 | 0.008955 | n/a — no positive pixels in this source; evaluator reports 0.0 by convention |
| zenodo_part2_no_oil (hard negative) | 1008 | 0.000005 | n/a — no positive pixels in this source; evaluator reports 0.0 by convention |

The near-zero FP-pixel-rate on `no_oil` (0.000005) and low rate on `lookalike` (0.009) indicate the model is not indiscriminately flagging oil on hard negatives — it is discriminating, not just recalling.

**Threshold note:** `best_f1_threshold=0.806` (from a val-set PR-sweep at the best epoch) is meaningfully different from the naive default of 0.5, and higher precision (0.68→0.79 F1) is achievable by using it instead of 0.5. Any downstream inference/serving code should read this calibrated threshold rather than hardcoding 0.5. It is recorded in the checkpoint's freeze sidecar (`netra_baseline_v02_dac482fcd84a_best.pt.frozen.json`).

The **test split was never touched** during training, tuning, or this reporting — per the absolute rules, it remains reserved for a future, separate final evaluation pass.

---

## Scientific Status

**EXPERIMENTAL / UNVALIDATED.** This is a first real baseline, not a validated production model — no hyperparameter tuning occurred (by design, only one baseline was authorized), no test-set evaluation has been run, and no comparison against any other model/config exists yet.

---

## Remaining Issues

- **Test-set evaluation not yet run.** By design, the test split (152 scenes / 2,432 tiles) has not been touched. A single, final, un-tuned evaluation pass against it is the natural next step before any claim of real-world performance.
- `encoder_weights: null` — the model trained from scratch. ImageNet initialization was not attempted this run because the C: cache was full at the time; caches are now redirected to D: for future runs, so this remains available as a future ablation, not a defect in this run.
- Work remains uncommitted on `feat/netra-real-training`, now that the baseline has completed cleanly and produced a frozen checkpoint. Committing is a decision for the user, not made automatically.
- The by-source IoU convention (0.0 for sources with no positive pixels, rather than `null`/`n/a`) is a known evaluator quirk worth fixing for report clarity, though it does not affect the overall/`zenodo_part1` metrics above, which are the ones that matter for oil-detection performance.
- Out of scope for this pass (NETRA only, per instruction): CHHAYA, AIS ingestion, ERA5/CMEMS integration.

---

## FINAL DECISION

# BASELINE COMPLETE

All data-engineering gates (Phases 4–24) passed. All five critical smoke-test conditions passed (loss measured, weights changed, metrics dynamic, GPU used, checkpoint reloads). The single authorized baseline is training unattended, detached, and resumable on the full corrected NETRA-GOLD-v0.2 dataset.
