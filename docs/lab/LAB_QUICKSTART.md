# VARUNA GRID v2 — Lab Quickstart Guide

> **Goal**: Get a college GPU machine ready for VARUNA training in under 5 minutes.  
> **Scientific Status**: `EXPERIMENTAL / UNVALIDATED`  
> **Required Python**: 3.12.x  
> **Tag**: `varuna-lab-ready-v1`

---

## 1. Clone & Environment Setup

```bash
git clone <repo-url> VARUNA
cd VARUNA
git checkout varuna-lab-ready-v1    # exact frozen state

# Install dependencies (use uv — recommended)
uv sync --extra ml --extra data --extra dev
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

Place raw datasets (Sentinel-1, AIS, ERA5, etc.) into `data/raw/`:

```
data/raw/sentinel1/    — SAR GRD scenes
data/raw/ais/          — Vessel tracks
data/raw/era5/         — Atmospheric forcing
data/raw/cmems/        — Ocean currents
data/raw/zenodo/       — Oil Spill Benchmark (if available)
```

Then run the data pipeline:

```bash
# 1. Validate raw data integrity
python scripts/validate_data.py

# 2. Convert raw → Silver canonical representations
python scripts/build_canonical.py

# 3. Build dataset lineage manifest
python scripts/build_manifest.py

# 4. Generate tiled, normalized Gold ML tensors
python scripts/build_gold.py
```

Then train:

```bash
# 5. Train NETRA (SAR Oil Spill Segmentation)
python train_netra.py --config configs/lab/netra.yaml

# 6. Train CHHAYA (Dark Vessel Trajectory Reconstruction)
python train_chhaya.py --config configs/lab/chhaya.yaml
```

---

## Troubleshooting

See [LAB_TROUBLESHOOTING.md](LAB_TROUBLESHOOTING.md) for common issues.

| Issue | Fix |
|---|---|
| `ModuleNotFoundError: varuna_*` | Run `uv sync` or set `PYTHONPATH=packages:.` |
| `segmentation_models_pytorch` warning | Install with `uv sync --extra ml` |
| GPU not detected | Verify NVIDIA drivers + CUDA toolkit match PyTorch build |
| Python < 3.12 errors (`StrEnum`) | **Must use Python 3.12.x** |
