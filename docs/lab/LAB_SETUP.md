# VARUNA GRID v2 — Laboratory Machine Setup Guide

This document details the system prerequisites, driver configuration, environment provisioning, and validation steps for running VARUNA GRID v2 on a physical laboratory workstation or server.

---

## 1. Target Hardware Requirements

| Hardware Component | Minimum Requirement | Recommended Lab Standard |
| :--- | :--- | :--- |
| **GPU** | NVIDIA GPU (>= 8 GB VRAM) | NVIDIA RTX 3060 / 4060 / 4070 / A4000 (12–16 GB VRAM) |
| **CUDA Compute** | Compute Capability >= 7.5 (Turing+) | Compute Capability >= 8.6 (Ampere / Ada Lovelace) |
| **System RAM** | 16 GB | 32 GB – 64 GB DDR4/DDR5 |
| **CPU** | 4 Cores (x86_64) | 8–16 Cores (Intel Core i7/i9 or AMD Ryzen 7/9) |
| **Storage** | 100 GB Free Space | 500 GB+ NVMe SSD (for raw SAR rasters & Gold tiles) |
| **Operating System**| Linux (Ubuntu 22.04 LTS) / Windows 11 | Ubuntu 22.04 / 24.04 LTS or WSL2 |

---

## 2. NVIDIA Driver & CUDA Setup

### Linux (Ubuntu 22.04 / 24.04)
```bash
# Check GPU presence
lspci | grep -i nvidia

# Install recommended NVIDIA proprietary driver (535 or higher)
sudo apt update
sudo apt install -y nvidia-driver-535 nvidia-utils-535

# Verify driver and CUDA driver version
nvidia-smi
```

### Windows 11 / WSL2
1. Download and install latest NVIDIA Game Ready / Studio driver from [nvidia.com/drivers](https://www.nvidia.com/drivers).
2. Open PowerShell and verify:
```powershell
nvidia-smi
```

---

## 3. Python & Package Management

We recommend using `uv` (fast Python package manager) or standard `python -m venv`.

### Using `uv` (Recommended)
```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install uv (Windows PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Sync dependencies including ML and dev packages
uv sync --extra ml --extra dev --extra data
```

### Using Standard `pip`
```bash
# Create virtual environment with Python >= 3.12
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Upgrade build tools
pip install --upgrade pip setuptools wheel

# Install editable package with ML extras
pip install -e ".[dev,ml,data]"
```

---

## 4. PyTorch CUDA Verification

Ensure PyTorch is built with CUDA support matching your driver:

```python
import torch
print("PyTorch Version :", torch.__version__)
print("CUDA Available  :", torch.cuda.is_available())
print("Device Count    :", torch.cuda.device_count())
if torch.cuda.is_available():
    print("Device Name     :", torch.cuda.get_device_name(0))
```

If PyTorch was installed as CPU-only, reinstall the CUDA build:
```bash
# Example for CUDA 12.1:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

## 5. Directory Initialization & Validation

Run the automated bootstrap script to create the Medallion directory tiers and verify read/write permissions:

```bash
python scripts/lab_bootstrap.py
```

Expected output:
- `[PASS] Python Version`
- `[PASS] PyTorch Version`
- `[PASS] CUDA Available`
- `[PASS] Directory Hierarchy: 20 directories verified (read/write OK)`
- Missing datasets will be reported as `NOT PROVIDED` (this is expected on a fresh machine).
