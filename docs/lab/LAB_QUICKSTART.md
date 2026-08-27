# VARUNA GRID v2 — Lab Quickstart Guide

> **Goal**: Get a college GPU machine ready for VARUNA training in under 5 minutes.  
> **Scientific Status**: `EXPERIMENTAL / UNVALIDATED`

---

## 1. Clone & Environment Setup

```bash
git clone <repo-url> VARUNA
cd VARUNA

# Install dependencies (use uv or pip)
uv sync --extra ml
# or: pip install -e ".[dev,ml,data]"
```

---

## 2. Verify Lab Hardware & Pipeline Readiness

Run the 4 automated diagnostic scripts in order:

```bash
# Step A: Environment & Directory Bootstrap (Verifies Python, Torch, RAM, Disk, Dirs)
python scripts/lab_bootstrap.py

# Step B: GPU & CUDA Acceleration Check (Verifies VRAM and GPU tensor computation)
python scripts/check_gpu.py

# Step C: Complete System Status
python scripts/lab_status.py

# Step D: Offline Synthetic Smoke Test (Tests full M6 data pipeline + NETRA/CHHAYA tensors)
python scripts/lab_smoke_test.py
```

---

## 3. Run Initial Smoke Training (0 Real Data Required)

Verify that model initialization, dataloaders, training loops, checkpoints, and experiment tracking are functional:

```bash
# NETRA SAR Segmentation Smoke Training (1-2 epochs)
python scripts/smoke_train_netra.py

# CHHAYA Dark Vessel Trajectory Smoke Training (1-2 epochs)
python scripts/smoke_train_chhaya.py
```

---

## 4. Ingest Real Datasets & Full Training

Once raw datasets (Sentinel-1, Zenodo, AIS, ERA5) are placed into `data/raw/`:

```bash
# 1. Validate raw data integrity
python scripts/validate_data.py

# 2. Convert raw data into canonical representations (Bronze -> Silver)
python scripts/build_canonical.py

# 3. Build dataset lineage manifest
python scripts/build_manifest.py

# 4. Generate tiled, normalized ML Gold tensors (Silver -> Gold)
python scripts/build_gold.py

# 5. Train NETRA & CHHAYA on Gold datasets
python train_netra.py --config configs/lab/netra.yaml
python train_chhaya.py --config configs/lab/chhaya.yaml
```
