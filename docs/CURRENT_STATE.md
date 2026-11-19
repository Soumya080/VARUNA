# VARUNA GRID v2 — Current State

**Last updated:** 2026-09-01T14:30 IST  
**Branch:** `feat/netra-real-training`  
**Auditor:** Session takeover reconstruction

## Live Processes
- **NETRA v0.3-B1 training:** ✅ COMPLETED (30/30 epochs, 59225.8s, `last.pt` saved 2026-09-01 10:00 AM)
- **All other processes (API, frontend, DB, Redis, MinIO):** ⚪ STOPPED
- **GPU:** IDLE (9W, 1122 MiB base)

## Active Experiment
- NETRA v0.3-B1 (`pilot_01_run2`): COMPLETED, AWAITING EVALUATION
- Checkpoint: `artifacts/experiments/netra_v03/pilot_01_run2/last.pt` (280 MB)
- No `best.pt` saved (early stopping was DISABLED by design)

## Completed Tracks
- ✅ Track 2 (PRATIVARTAN/NYAYA/Validity/AIS/ERA5/CMEMS): FROZEN
- ✅ Case Engine reconciliation (GoldenCaseWorkflow canonical)
- ✅ Mission/ABHIYAN/Alerts decision-state mapping
- ✅ PRAVAAH canonical integration (pipeline._forecast wired)

## Current Blocker
- **B1 evaluation not done** — training just finished; no CALM-GRD-HOLDOUT metrics exist yet

## Current Next Action
1. Run CALM-GRD-HOLDOUT evaluation on `last.pt` (v0.3-B1)
2. Compare against v0.2 baseline (IoU 0.6458, PR-AUC 0.8513)
3. Evaluate source-domain preservation + MC20 external
4. Classify result: SUCCESS / PARTIAL / NO_GAIN / REGRESSION / FAILED

## Next Dependency
- Evaluation script (write or locate)
- v0.2 frozen checkpoint for comparison

## Do-Not-Touch List
- v0.2 checkpoint (`netra_baseline_v02_dac482fcd84a_best.pt`)
- Track 2 code (FROZEN)
- B1 training artifacts (DO NOT RERUN)
- Frontend (owned by another engineer)
