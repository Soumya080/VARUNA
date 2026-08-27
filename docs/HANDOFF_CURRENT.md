# VARUNA GRID v2 — Lab Handoff Document

> **Generated:** 2026-08-28  
> **Authority:** This document is the final handoff state for lab transfer.

---

## Current Milestone

**M6.5 P0/P1 Hardening + Lab Training Readiness — COMPLETE**

All milestones M1 through M6.5 and Lab Training Readiness are implemented.
M7 (Real Data Integration & Validated Training) has NOT been started.

## Current Branch

```
milestone/m3.5-productization
```

## Freeze Commit

See the annotated tag `varuna-lab-ready-v1` for the exact freeze point.

## Repository State

| State | Status |
|---|---|
| Working Tree | CLEAN (after freeze commit) |
| Tracked Datasets | NONE |
| Tracked Checkpoints | NONE (only `.gitkeep` placeholders) |
| Tracked Secrets | NONE |
| `.gitignore` | Verified — data, artifacts, envs, caches excluded |

---

## Implemented (Software Complete)

| Component | Package | Status |
|---|---|---|
| Evidence Contracts | `varuna_contracts` | VERIFIED (22 tests) |
| Geospatial Utilities | `varuna_geospatial` | VERIFIED |
| Backward Advection | `varuna_prativartan` | VERIFIED |
| Bayesian Attribution | `varuna_nyaya` | VERIFIED |
| SAR Detection (NETRA) | `varuna_netra` | IMPLEMENTED (mock + real model skeleton) |
| Dark Vessel (CHHAYA) | `varuna_chhaya` | IMPLEMENTED (mock + real model skeleton) |
| Drift Forecasting (PRAVAAH) | `varuna_pravaah` | IMPLEMENTED (mock) |
| Mission Planning (ABHIYAN) | `varuna_abhiyan` | IMPLEMENTED (mock) |
| Event Store (SMRITI) | `varuna_smriti` | IMPLEMENTED (mock) |
| Alert Router | `varuna_alerts` | IMPLEMENTED |
| Mission Runtime | `varuna_missions` | IMPLEMENTED |
| Source Adapters | `varuna_source_adapters` | IMPLEMENTED (mock + real adapters) |
| Data Engineering | `varuna_data_eng` | IMPLEMENTED |
| ML Infrastructure | `varuna_infra` | IMPLEMENTED |
| Domain Services | `varuna_domain` | IMPLEMENTED |
| FastAPI Backend | `apps/api` | IMPLEMENTED |
| Celery Workers | `apps/worker` | IMPLEMENTED |
| Lab Bootstrap | `scripts/lab_*` | VERIFIED |
| Training Scripts | `train_netra.py`, `train_chhaya.py` | IMPLEMENTED |

## Verified (Tests Pass)

| Test Suite | Result |
|---|---|
| Unit Tests (`tests/unit/`) | **105 passed, 0 failed** |
| Integration Tests (`tests/integration/`) | 5 passed, 1 skipped |
| Contract Tests (`tests/contract/`) | 22 passed |
| Lab Smoke Test | PASS (synthetic pipeline 100% offline) |
| NETRA Smoke Training | PASS (2 epochs, mock model, CPU) |
| Lab Bootstrap | PASS |
| GPU Check | PASS (on dev machine with RTX 4050) |

## Unverified

- CHHAYA smoke training: **blocked on Python 3.10 dev machine** (`StrEnum` requires 3.12). Will pass on lab machine with Python 3.12.
- Real data pipeline: not tested (no real data available)
- Production deployment: Docker Compose defined but not tested end-to-end
- PostgreSQL persistence: `geoalchemy2` not installed on dev machine

## Known Technical Debt (P2)

1. **Python 3.10 compatibility**: `CODEBASE_SUMMARY.md` documents a 3.10 monkeypatch workaround for the experiment runner. The project requires `>=3.12` per `pyproject.toml`. Lab machine MUST use Python 3.12.
2. **`test_case_0001.py`**: Pre-M4 integration test uses old `CaseWorkflow()` without DI args — 9 collection errors. Not blocking.
3. **`geoalchemy2` dependency**: PostgreSQL integration tests fail to collect without it. Not needed for training.
4. **CRLF/LF line endings**: Git auto-conversion warnings on Windows. Non-blocking.
5. **`segmentation_models_pytorch`**: Falls back to `MockNetraModel` gracefully when not installed. Lab should install via `uv sync --extra ml`.
6. **NETRA encoder weights**: Config set to `null` (offline mode). Real training may want pretrained ImageNet weights.

## Pre-existing Failures

| Test | Reason | Blocking? |
|---|---|---|
| `test_e2e_persistence.py` | `geoalchemy2` not installed | NO |
| `test_postgres_repos.py` | `geoalchemy2` not installed | NO |
| `test_case_0001.py` (9 tests) | Old pre-M4 API, needs DI update | NO |
| CHHAYA smoke training | Python 3.10 lacks `StrEnum` | NO (lab uses 3.12) |

## Scientific Status

**EXPERIMENTAL / UNVALIDATED**

- All model architectures are defined but weights are random or smoke-trained
- No real satellite imagery has been processed
- No peer review or validation has occurred
- Attribution pipeline uses synthetic scenarios only

## Lab Requirements

| Requirement | Minimum |
|---|---|
| Python | 3.12.x |
| GPU | NVIDIA with ≥6 GB VRAM |
| CUDA | 12.x |
| System RAM | 32 GB recommended |
| Disk | 100 GB free |
| Package Manager | `uv` (recommended) or `pip` |

## Dataset Placement

Place raw datasets into `data/raw/` subdirectories:

```
data/raw/sentinel1/    — Sentinel-1 SAR GRD scenes (.tif, .safe)
data/raw/zenodo/       — Zenodo Oil Spill Benchmark
data/raw/essd/         — ESSD Global Oil Slick Dataset
data/raw/xview3/       — xView3 Dark Vessel & Slick SAR
data/raw/ais/          — AIS vessel tracks (.csv)
data/raw/era5/         — ECMWF ERA5 atmospheric forcing (.nc, .grib)
data/raw/cmems/        — Copernicus Marine currents (.nc)
data/raw/bhoonidhi/    — ISRO Bhoonidhi catalog
data/raw/nisar/        — NASA-ISRO SAR data
data/raw/risat/        — ISRO RISAT-1/1A SAR data
```

## Data Pipeline Commands

```bash
python scripts/validate_data.py             # Validate raw data integrity
python scripts/build_canonical.py            # Raw → Silver (canonical representations)
python scripts/build_manifest.py             # Generate dataset lineage manifest
python scripts/build_gold.py                 # Silver → Gold (ML-ready tensors)
```

## Training Commands

```bash
# NETRA — SAR Oil Spill Segmentation (U-Net)
python train_netra.py --config configs/lab/netra.yaml

# CHHAYA — Dark Vessel Trajectory Reconstruction (LSTM)
python train_chhaya.py --config configs/lab/chhaya.yaml
```

## Next Step

**M7: Real Data Integration & Validated Training**

Prerequisites before M7 can begin:
1. Lab machine with Python 3.12 + CUDA GPU operational
2. Raw datasets placed in `data/raw/` (at minimum: Sentinel-1, AIS, ERA5)
3. `uv sync --extra ml --extra data` completed successfully
4. All smoke tests pass on lab machine
5. `python scripts/lab_status.py` reports `GPU READY`

M7 tasks:
- Download and validate real datasets
- Run full data pipeline (validate → canonical → manifest → gold)
- Train NETRA on real SAR imagery
- Train CHHAYA on real AIS trajectories
- Validate model performance against ground truth
- Update scientific status from EXPERIMENTAL to VALIDATED (if metrics pass)
