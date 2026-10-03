"""
VARUNA GRID v2 — Comprehensive Lab Status Report.

Aggregates overall laboratory readiness:
1. Repository & Git state
2. Python & PyTorch environment
3. CUDA & GPU hardware details
4. Memory (RAM) & Disk space
5. Data directory status across Medallion layers (Raw, Bronze, Silver, Gold, Manifests)
6. Training configurations verification (configs/lab/netra.yaml, configs/lab/chhaya.yaml)
7. Synthetic pipeline readiness and test status

Usage:
    python scripts/lab_status.py
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from typing import Dict, Any, List

from scripts.lab_bootstrap import (
    check_python,
    check_torch_and_cuda,
    check_system_resources,
    check_git_state,
    scan_raw_datasets,
    REQUIRED_DIRECTORIES,
)
from scripts.check_gpu import run_gpu_check


def check_training_configs(base_dir: Path) -> Dict[str, Any]:
    """Inspects lab training configuration YAML files."""
    configs = {}
    config_paths = [
        ("netra", base_dir / "configs" / "lab" / "netra.yaml"),
        ("chhaya", base_dir / "configs" / "lab" / "chhaya.yaml"),
    ]

    for name, path in config_paths:
        if not path.exists():
            configs[name] = {"exists": False, "path": str(path), "size_bytes": 0}
        else:
            configs[name] = {
                "exists": True,
                "path": str(path),
                "size_bytes": path.stat().st_size,
            }
    return configs


def check_data_and_artifact_status(base_dir: Path) -> Dict[str, Any]:
    """Scans counts and sizes across data/ and artifacts/ subdirectories."""
    summary = {}
    for rel_dir in REQUIRED_DIRECTORIES:
        p = base_dir / rel_dir
        if not p.exists():
            summary[rel_dir] = {"exists": False, "file_count": 0, "size_bytes": 0}
        else:
            files = [f for f in p.rglob("*") if f.is_file() and not f.name.startswith(".")]
            total_size = sum(f.stat().st_size for f in files)
            summary[rel_dir] = {
                "exists": True,
                "file_count": len(files),
                "size_bytes": total_size,
            }
    return summary


def get_lab_status(base_dir: Path | None = None) -> Dict[str, Any]:
    """Collects comprehensive lab status."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    git_info = check_git_state(base_dir)
    py_info = check_python()
    gpu_info = run_gpu_check()
    res_info = check_system_resources(base_dir)
    data_status = check_data_and_artifact_status(base_dir)
    raw_inv = scan_raw_datasets(base_dir)
    cfg_status = check_training_configs(base_dir)

    return {
        "base_dir": str(base_dir),
        "git": git_info,
        "python": py_info,
        "gpu": gpu_info,
        "resources": res_info,
        "data_dirs": data_status,
        "raw_inventory": raw_inv,
        "training_configs": cfg_status,
    }


def print_lab_status(status: Dict[str, Any]) -> None:
    """Prints the formatted lab status report."""
    print("=" * 70)
    print(" VARUNA GRID v2 — LAB SYSTEM & TRAINING READINESS STATUS")
    print("=" * 70)

    # 1. Repo & Git
    git = status["git"]
    if git["is_repo"]:
        dirty = " [DIRTY]" if git["is_dirty"] else " [CLEAN]"
        print(f"Git Branch        : {git['branch']} ({git['commit']}){dirty}")
    else:
        print("Git Branch        : Non-git checkout")

    # 2. Python & PyTorch
    py = status["python"]
    print(f"Python Runtime    : {py['version']} ({py['platform']})")
    
    gpu = status["gpu"]
    if gpu["torch_installed"]:
        print(f"PyTorch Version   : {gpu['torch_version']}")
    else:
        print("PyTorch Version   : NOT INSTALLED")

    # 3. CUDA & GPU
    if gpu["cuda_available"]:
        print(f"CUDA Version      : {gpu['pytorch_cuda_version']} (Available: TRUE)")
        for dev in gpu["devices"]:
            print(f"GPU Hardware      : [{dev['id']}] {dev['name']} ({dev['total_vram_gb']} GB VRAM)")
    else:
        print("CUDA / GPU        : CUDA UNAVAILABLE / CPU ONLY")
        smi = gpu.get("nvidia_smi", {})
        if smi.get("nvidia_smi_found") and smi.get("gpus"):
            print(f"Host GPU (Driver) : {smi['driver_version']} — {smi['gpus'][0]['name']}")

    # 4. Resources
    res = status["resources"]
    print(f"Host Memory (RAM) : {res['ram_available_gb']} GB available / {res['ram_total_gb']} GB total")
    print(f"Disk Storage      : {res['disk_free_gb']} GB free / {res['disk_total_gb']} GB total")

    # 5. Training Configs
    print("\n" + "-" * 70)
    print(" TRAINING CONFIGURATIONS (configs/lab/)")
    print("-" * 70)
    for name, cfg in status["training_configs"].items():
        state = "FOUND" if cfg["exists"] else "MISSING"
        print(f"  * {name:<10} : {state:<8} ({cfg['path']})")

    # 6. Data Directory Medallion Layers
    print("\n" + "-" * 70)
    print(" DATA STORAGE TIERS (data/)")
    print("-" * 70)
    for path_key, info in status["data_dirs"].items():
        if path_key.startswith("data/"):
            fc = info["file_count"]
            sz_mb = info["size_bytes"] / (1024 * 1024)
            print(f"  * {path_key:<26} : {fc:>4} files ({sz_mb:>8.2f} MB)")

    # 7. Artifacts
    print("\n" + "-" * 70)
    print(" ARTIFACT STORAGE TIERS (artifacts/)")
    print("-" * 70)
    for path_key, info in status["data_dirs"].items():
        if path_key.startswith("artifacts/"):
            fc = info["file_count"]
            sz_mb = info["size_bytes"] / (1024 * 1024)
            print(f"  * {path_key:<26} : {fc:>4} files ({sz_mb:>8.2f} MB)")

    print("=" * 70)
    ready = gpu["training_ready"]
    train_status = "GPU READY" if ready else "CPU ONLY (GPU NOT READY)"
    print(f" OVERALL TRAINING PIPELINE STATUS : {train_status}")
    print("=" * 70)


if __name__ == "__main__":
    st = get_lab_status()
    print_lab_status(st)
    sys.exit(0)
