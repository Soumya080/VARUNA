"""
VARUNA GRID v2 — GPU & CUDA Diagnostics Script.

Inspects hardware acceleration for deep learning (NETRA / CHHAYA):
- CUDA driver and runtime version
- PyTorch CUDA build compatibility
- GPU device enumeration, name, compute capability, and VRAM
- Executes a real tensor computation on GPU (if present)
- Reports TRAINING_READY = TRUE / FALSE clearly without faking success.

Usage:
    python scripts/check_gpu.py
"""

from __future__ import annotations

import sys
import shutil
import subprocess
from typing import Dict, Any, List


def check_system_nvidia_smi() -> Dict[str, Any]:
    """Queries nvidia-smi tool if present on PATH or standard driver locations."""
    res = {
        "nvidia_smi_found": False,
        "driver_version": None,
        "cuda_driver_version": None,
        "gpus": [],
        "raw_output": None,
    }

    smi_path = shutil.which("nvidia-smi")
    if not smi_path and sys.platform == "win32":
        # Check standard Windows NVIDIA driver folder
        win_path = r"C:\Windows\System32\nvidia-smi.exe"
        if shutil.os.path.exists(win_path):
            smi_path = win_path

    if smi_path:
        res["nvidia_smi_found"] = True
        try:
            out = subprocess.check_output(
                [smi_path, "--query-gpu=index,name,driver_version,memory.total,memory.free", "--format=csv,noheader,nounits"],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
            res["raw_output"] = out
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    res["gpus"].append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "driver_version": parts[2],
                        "memory_total_mb": float(parts[3]),
                        "memory_free_mb": float(parts[4]),
                    })
                    if not res["driver_version"]:
                        res["driver_version"] = parts[2]
        except Exception:
            pass

    return res


def run_gpu_check() -> Dict[str, Any]:
    """Runs complete GPU diagnostics and mini tensor computation."""
    smi_info = check_system_nvidia_smi()

    diag: Dict[str, Any] = {
        "torch_installed": False,
        "torch_version": None,
        "cuda_available": False,
        "pytorch_cuda_version": None,
        "device_count": 0,
        "devices": [],
        "computation_success": False,
        "computation_error": None,
        "training_ready": False,
        "nvidia_smi": smi_info,
    }

    try:
        import torch
        diag["torch_installed"] = True
        diag["torch_version"] = torch.__version__
        diag["cuda_available"] = bool(torch.cuda.is_available())
        diag["pytorch_cuda_version"] = getattr(torch.version, "cuda", None)

        if torch.cuda.is_available():
            diag["device_count"] = torch.cuda.device_count()
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                mem_total_gb = props.total_memory / (1024 ** 3)
                mem_allocated_gb = torch.cuda.memory_allocated(i) / (1024 ** 3)
                mem_reserved_gb = torch.cuda.memory_reserved(i) / (1024 ** 3)

                diag["devices"].append({
                    "id": i,
                    "name": props.name,
                    "total_vram_gb": round(mem_total_gb, 2),
                    "allocated_vram_gb": round(mem_allocated_gb, 2),
                    "reserved_vram_gb": round(mem_reserved_gb, 2),
                    "compute_capability": f"{props.major}.{props.minor}",
                })

            # Run tiny GPU tensor computation
            try:
                device = torch.device("cuda:0")
                a = torch.randn(256, 256, device=device, dtype=torch.float32)
                b = torch.randn(256, 256, device=device, dtype=torch.float32)
                c = torch.matmul(a, b)
                torch.cuda.synchronize()
                if c.shape == (256, 256):
                    diag["computation_success"] = True
                    diag["training_ready"] = True
            except Exception as e:
                diag["computation_error"] = str(e)
                diag["computation_success"] = False
                diag["training_ready"] = False
        else:
            diag["training_ready"] = False
    except ImportError:
        diag["training_ready"] = False

    return diag


def print_gpu_report(diag: Dict[str, Any]) -> None:
    """Prints diagnostic report to console."""
    print("=" * 65)
    print(" VARUNA GRID v2 — GPU & CUDA DIAGNOSTIC REPORT")
    print("=" * 65)

    # PyTorch
    if diag["torch_installed"]:
        print(f"[PASS] PyTorch Installed   : TRUE ({diag['torch_version']})")
    else:
        print("[FAIL] PyTorch Installed   : FALSE")

    # CUDA in PyTorch
    if diag["cuda_available"]:
        print(f"[PASS] PyTorch CUDA        : TRUE (Built with CUDA {diag['pytorch_cuda_version']})")
        print(f"       GPU Devices         : {diag['device_count']}")
        for dev in diag["devices"]:
            print(f"       * Device [{dev['id']}]: {dev['name']}")
            print(f"         Compute Capability : {dev['compute_capability']}")
            print(f"         Total VRAM         : {dev['total_vram_gb']} GB")
            print(f"         Allocated VRAM     : {dev['allocated_vram_gb']} GB")
    else:
        print("[INFO] PyTorch CUDA        : FALSE (No CUDA-enabled GPU detected by PyTorch)")

    # System nvidia-smi
    smi = diag["nvidia_smi"]
    if smi["nvidia_smi_found"] and smi["gpus"]:
        print(f"[INFO] System NVIDIA Driver: {smi['driver_version']}")
        for gpu in smi["gpus"]:
            print(f"       * nvidia-smi GPU {gpu['index']}: {gpu['name']} ({gpu['memory_total_mb'] / 1024:.2f} GB total, {gpu['memory_free_mb'] / 1024:.2f} GB free)")
    else:
        print("[INFO] System nvidia-smi   : Not found or no NVIDIA GPUs reported")

    # Tensor computation
    if diag["cuda_available"]:
        if diag["computation_success"]:
            print("[PASS] Tensor Computation  : PASSED (256x256 matmul verified on cuda:0)")
        else:
            print(f"[FAIL] Tensor Computation  : FAILED ({diag['computation_error']})")

    print("-" * 65)
    if diag["training_ready"]:
        print(" TRAINING_READY = TRUE  (GPU acceleration is operational)")
    else:
        print(" TRAINING_READY = FALSE (GPU acceleration is NOT operational)")
        if not diag["torch_installed"]:
            print(" -> Reason: PyTorch is not installed. Run 'uv sync --extra ml' or 'pip install -e .[ml]'.")
        elif not diag["cuda_available"]:
            print(" -> Reason: PyTorch does not see a CUDA GPU. Check NVIDIA drivers & PyTorch CUDA build.")
        elif not diag["computation_success"]:
            print(f" -> Reason: GPU tensor computation failed: {diag['computation_error']}")
    print("=" * 65)


if __name__ == "__main__":
    diagnostics = run_gpu_check()
    print_gpu_report(diagnostics)
    # The script reports diagnostics clearly and exits 0 for normal reporting
    sys.exit(0)
