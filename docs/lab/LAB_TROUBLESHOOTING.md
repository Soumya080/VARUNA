# VARUNA GRID v2 — Laboratory Troubleshooting Guide

Solutions to common issues encountered during laboratory setup, data pipeline processing, and model training.

---

## 1. Environment & Hardware Issues

### Issue 1.1: `TRAINING_READY = FALSE` / GPU Not Detected
- **Symptom**: `scripts/check_gpu.py` outputs `TRAINING_READY = FALSE (GPU acceleration is NOT operational)`.
- **Cause**: PyTorch was installed with CPU-only wheels or NVIDIA GPU drivers are missing.
- **Fix**:
  1. Check if `nvidia-smi` works on the command line. If not, install the latest NVIDIA drivers.
  2. Reinstall PyTorch with CUDA support:
     ```bash
     pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
     ```
  3. Re-run `python scripts/check_gpu.py`.

### Issue 1.2: CUDA Out-Of-Memory (`torch.cuda.OutOfMemoryError`)
- **Symptom**: Training crashes during backward pass with CUDA OOM.
- **Fix**:
  1. Reduce `batch_size` in `configs/lab/netra.yaml` (e.g. from `4` to `2` or `1`).
  2. Increase `gradient_accumulation` (e.g. from `2` to `4`) to preserve effective batch size.
  3. Ensure `mixed_precision: true` is enabled in your config.
  4. Reduce `image_size` from `512` to `256`.

---

## 2. Data Pipeline Issues

### Issue 2.1: `NOT PROVIDED` Datasets
- **Symptom**: `scripts/lab_bootstrap.py` or `scripts/validate_data.py` reports `NOT PROVIDED` for some or all datasets in `data/raw/`.
- **Cause**: Raw datasets have not yet been downloaded or placed into `data/raw/`.
- **Fix**:
  - This is expected behavior on fresh lab machines. Missing datasets do **NOT** fail the bootstrap.
  - You can run the entire pipeline offline on synthetic data using `python scripts/lab_smoke_test.py` or `python scripts/build_gold.py`.
  - When real data arrives, place it in the appropriate `data/raw/<source>/` folder and run `python scripts/validate_data.py`.

### Issue 2.2: Data Leakage Error (`ValueError: Data Leakage detected!`)
- **Symptom**: `FullPipeline` raises a Data Leakage exception during dataset splitting.
- **Cause**: A scene or geographic area is assigned to both Train and Val/Test splits.
- **Fix**:
  - Check the `split_strategy` in your configuration (`geographic_temporal` or `hash_random`).
  - Ensure that scenes in different splits have sufficient geographic and temporal separation.

---

## 3. Training & Model Issues

### Issue 3.1: Offline Machine Cannot Download Pretrained Weights
- **Symptom**: `urllib.error.URLError` when initializing the encoder backbone (e.g. ResNet34 from PyTorch Hub or Timm).
- **Cause**: Lab machine is air-gapped or has restricted internet access.
- **Fix**:
  - In `configs/lab/netra.yaml`, ensure `encoder_weights: null` (or `"none"`) is set to train from scratch without external downloads.
  - Or manually download weights from an internet-connected machine and place them under `models/pretrained/`.

### Issue 3.2: Corrupt or Empty Checkpoints
- **Symptom**: Loading checkpoint fails with `EOFError` or invalid pickle header.
- **Fix**:
  - Verify disk space with `python scripts/lab_status.py`.
  - Delete corrupt partial checkpoint from `artifacts/checkpoints/` and restart training.
