# VARUNA GRID v2 — Laboratory Training Runbook

This runbook covers training execution for **NETRA** (SAR Oil Slick & Lookalike Segmentation) and **CHHAYA** (Dark Vessel AIS Trajectory Reconstruction).

---

## 1. Scientific Status & Disclaimers

> **IMPORTANT**:
> All scientific algorithms, loss functions, metrics, and models in VARUNA GRID v2 remain **EXPERIMENTAL / UNVALIDATED**.
> Smoke training scripts prove pipeline wiring (dataset -> dataloader -> model -> optimizer -> loss -> validation -> checkpoint -> registry).
> They do NOT represent scientifically validated accuracy or operational deployment clearance.

---

## 2. Training Configurations (`configs/lab/`)

Training configurations are located under `configs/lab/`:
- `configs/lab/netra.yaml`: Configuration for NETRA U-Net segmentation
- `configs/lab/chhaya.yaml`: Configuration for CHHAYA LSTM trajectory reconstruction

### Conservative Hardware Baseline (12 GB VRAM / 32 GB RAM):
```yaml
# configs/lab/netra.yaml snippet
batch_size: 4
gradient_accumulation: 2       # Effective batch size = 8
mixed_precision: true          # AMP FP16/BF16
image_size: 512
epochs: 25
learning_rate: 0.0003
num_workers: 4
checkpoint_dir: "artifacts/checkpoints/netra"
```

---

## 3. Running Training

### Smoke Training (Instant Pipeline Verification)
```bash
# Verify NETRA training loop
python scripts/smoke_train_netra.py

# Verify CHHAYA training loop
python scripts/smoke_train_chhaya.py
```

### Full Training on Gold Datasets
```bash
# Train NETRA
python train_netra.py --config configs/lab/netra.yaml

# Train CHHAYA
python train_chhaya.py --config configs/lab/chhaya.yaml

# Quick 1-epoch dry-run test
python train_netra.py --config configs/lab/netra.yaml --dry-run
python train_chhaya.py --config configs/lab/chhaya.yaml --dry-run
```

---

## 4. Checkpoints & Model Registry

Training artifacts are saved in two locations:
1. **Model Checkpoints**:
   - `artifacts/checkpoints/netra/<experiment_id>_best.pt`
   - `artifacts/checkpoints/chhaya/<experiment_id>_best.pt`
2. **Experiment Metadata & Logs**:
   - `artifacts/experiments/<experiment_id>.json`

### Traceability Metadata
Every training run logs:
- `experiment_id`: Unique run identifier (e.g. `exp_c762717c`)
- `model_name` & `model_version`
- `dataset_version`: Dataset manifest hash / version
- `git_commit`: Exact Git commit hash
- `config_hash`: SHA-256 hash of training parameters
- `seed`: Random seed
- `metrics`: Final validation metrics (IoU, Dice, F1 for NETRA; Mean Distance Error for CHHAYA)
- `timestamp`: UTC training timestamp

All trained models are registered with status `CANDIDATE` in `ModelRegistry` and are **never automatically deployed**.
