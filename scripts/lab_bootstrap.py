"""
VARUNA GRID v2 — Lab Bootstrap Script.

Verifies the lab machine environment for real dataset ingestion and NETRA/CHHAYA training:
1. Python version and runtime
2. Package manager (uv / pip)
3. PyTorch availability and version
4. CUDA runtime and GPU availability
5. System RAM and disk space
6. Git repository state and commit
7. Directory structure initialization (data/ and artifacts/)
8. Read/write directory permissions
9. Raw dataset inventory (reports 'NOT PROVIDED' for missing datasets without failing)

Usage:
    python scripts/lab_bootstrap.py
"""

from __future__ import annotations

import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple


REQUIRED_DIRECTORIES = [
    # Data medallion architecture
    "data/raw/sentinel1",
    "data/raw/zenodo",
    "data/raw/essd",
    "data/raw/xview3",
    "data/raw/ais",
    "data/raw/era5",
    "data/raw/cmems",
    "data/raw/bhoonidhi",
    "data/raw/nisar",
    "data/raw/risat",
    "data/bronze",
    "data/silver",
    "data/gold/netra",
    "data/gold/chhaya",
    "data/gold/attribution",
    "data/manifests",
    # Artifacts & Outputs
    "artifacts/models",
    "artifacts/checkpoints",
    "artifacts/experiments",
    "artifacts/reports",
]

RAW_DATASET_DIRS = [
    ("sentinel1", "Sentinel-1 SAR GRD scenes"),
    ("zenodo", "Zenodo Oil Spill Benchmark"),
    ("essd", "ESSD Global Oil Slick Dataset"),
    ("xview3", "xView3 Dark Vessel & Slick SAR"),
    ("ais", "Terrestrial / Satellite AIS tracks"),
    ("era5", "ECMWF ERA5 Atmospheric Forcing"),
    ("cmems", "Copernicus Marine Current / Ocean"),
    ("bhoonidhi", "ISRO Bhoonidhi Satellite Catalog"),
    ("nisar", "NASA-ISRO SAR Data"),
    ("risat", "ISRO RISAT-1/1A SAR Data"),
]


def check_python() -> Dict[str, Any]:
    """Inspects Python version and interpreter path."""
    version_info = sys.version_info
    version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    is_compatible = version_info.major == 3 and version_info.minor >= 12
    return {
        "version": version_str,
        "executable": sys.executable,
        "compatible": is_compatible,
        "platform": platform.platform(),
        "arch": platform.machine(),
    }


def check_package_manager() -> Dict[str, Any]:
    """Detects available package managers (uv, pip, conda)."""
    managers = {}
    for pm in ["uv", "pip", "conda"]:
        path = shutil.which(pm)
        if path:
            try:
                out = subprocess.check_output([pm, "--version"], text=True, stderr=subprocess.STDOUT).strip()
                managers[pm] = {"installed": True, "path": path, "version": out}
            except Exception:
                managers[pm] = {"installed": True, "path": path, "version": "unknown"}
        else:
            managers[pm] = {"installed": False, "path": None, "version": None}
    return managers


def check_torch_and_cuda() -> Dict[str, Any]:
    """Inspects PyTorch, CUDA, and GPU hardware."""
    info: Dict[str, Any] = {
        "torch_installed": False,
        "torch_version": None,
        "cuda_available": False,
        "cuda_version": None,
        "device_count": 0,
        "devices": [],
    }

    try:
        import torch
        info["torch_installed"] = True
        info["torch_version"] = torch.__version__
        info["cuda_available"] = bool(torch.cuda.is_available())
        info["cuda_version"] = getattr(torch.version, "cuda", None)
        
        if torch.cuda.is_available():
            info["device_count"] = torch.cuda.device_count()
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                total_mem_gb = props.total_memory / (1024 ** 3)
                info["devices"].append({
                    "id": i,
                    "name": props.name,
                    "total_memory_gb": round(total_mem_gb, 2),
                    "major": props.major,
                    "minor": props.minor,
                })
    except ImportError:
        pass

    return info


def check_system_resources(base_dir: Path) -> Dict[str, Any]:
    """Inspects system RAM and free disk space."""
    res: Dict[str, Any] = {
        "ram_total_gb": None,
        "ram_available_gb": None,
        "disk_total_gb": None,
        "disk_free_gb": None,
    }

    # RAM via psutil if present, or fallback
    try:
        import psutil
        mem = psutil.virtual_memory()
        res["ram_total_gb"] = round(mem.total / (1024 ** 3), 2)
        res["ram_available_gb"] = round(mem.available / (1024 ** 3), 2)
    except ImportError:
        try:
            if sys.platform == "win32":
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                res["ram_total_gb"] = round(stat.ullTotalPhys / (1024 ** 3), 2)
                res["ram_available_gb"] = round(stat.ullAvailPhys / (1024 ** 3), 2)
        except Exception:
            pass

    # Disk usage
    try:
        usage = shutil.disk_usage(base_dir)
        res["disk_total_gb"] = round(usage.total / (1024 ** 3), 2)
        res["disk_free_gb"] = round(usage.free / (1024 ** 3), 2)
    except Exception:
        pass

    return res


def check_git_state(base_dir: Path) -> Dict[str, Any]:
    """Inspects Git branch, commit hash, and dirty state."""
    state = {
        "is_repo": False,
        "branch": None,
        "commit": None,
        "is_dirty": False,
    }
    if not (base_dir / ".git").exists():
        return state

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir, text=True, stderr=subprocess.DEVNULL
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=base_dir, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=base_dir, text=True, stderr=subprocess.DEVNULL
        ).strip()

        state["is_repo"] = True
        state["branch"] = branch
        state["commit"] = commit
        state["is_dirty"] = len(status) > 0
    except Exception:
        pass

    return state


def init_and_verify_directories(base_dir: Path) -> Tuple[List[str], List[str]]:
    """Creates required lab directories and verifies read/write permissions."""
    created = []
    errors = []

    for rel_path in REQUIRED_DIRECTORIES:
        d = base_dir / rel_path
        try:
            d.mkdir(parents=True, exist_ok=True)
            # Create .gitkeep if missing
            gitkeep = d / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()
            # Test write permission
            test_file = d / ".perm_check.tmp"
            test_file.write_text("ok")
            test_file.unlink()
            created.append(rel_path)
        except Exception as e:
            errors.append(f"{rel_path}: {e}")

    return created, errors


def scan_raw_datasets(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Inspects raw dataset directories and reports status without failing."""
    inventory = {}
    for folder_name, desc in RAW_DATASET_DIRS:
        d = base_dir / "data" / "raw" / folder_name
        if not d.exists():
            inventory[folder_name] = {
                "description": desc,
                "status": "NOT PROVIDED",
                "file_count": 0,
                "size_bytes": 0,
            }
            continue

        # Count meaningful payload files (excluding .gitkeep and temp files)
        files = [f for f in d.rglob("*") if f.is_file() and not f.name.startswith(".")]
        if not files:
            inventory[folder_name] = {
                "description": desc,
                "status": "NOT PROVIDED",
                "file_count": 0,
                "size_bytes": 0,
            }
        else:
            total_size = sum(f.stat().st_size for f in files)
            inventory[folder_name] = {
                "description": desc,
                "status": f"READY ({len(files)} files)",
                "file_count": len(files),
                "size_bytes": total_size,
            }
    return inventory


def run_bootstrap(base_dir: Path | None = None) -> Dict[str, Any]:
    """Runs all bootstrap checks, initializes directory structure, and returns diagnostic dict."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    python_info = check_python()
    pm_info = check_package_manager()
    torch_info = check_torch_and_cuda()
    sys_info = check_system_resources(base_dir)
    git_info = check_git_state(base_dir)
    created_dirs, dir_errors = init_and_verify_directories(base_dir)
    raw_inventory = scan_raw_datasets(base_dir)

    all_passed = (
        python_info["compatible"]
        and len(dir_errors) == 0
    )

    return {
        "all_passed": all_passed,
        "base_dir": str(base_dir),
        "python": python_info,
        "package_managers": pm_info,
        "torch_cuda": torch_info,
        "resources": sys_info,
        "git": git_info,
        "directories_initialized": len(created_dirs),
        "directory_errors": dir_errors,
        "raw_inventory": raw_inventory,
    }


def print_report(res: Dict[str, Any]) -> None:
    """Prints a structured, formatted lab bootstrap summary."""
    print("=" * 65)
    print(" VARUNA GRID v2 — LAB BOOTSTRAP ENVIRONMENT REPORT")
    print("=" * 65)
    
    # Python
    py = res["python"]
    status_py = "PASS" if py["compatible"] else "FAIL"
    print(f"[{status_py}] Python Version     : {py['version']} ({py['executable']})")
    print(f"       OS Platform        : {py['platform']} ({py['arch']})")

    # Package Manager
    pms = res["package_managers"]
    pm_strs = [k for k, v in pms.items() if v["installed"]]
    print(f"[INFO] Package Managers   : {', '.join(pm_strs) if pm_strs else 'none detected'}")

    # PyTorch & CUDA
    tc = res["torch_cuda"]
    if tc["torch_installed"]:
        print(f"[PASS] PyTorch Version    : {tc['torch_version']}")
    else:
        print("[WARN] PyTorch            : NOT INSTALLED (Run 'uv sync' or 'pip install -e .[ml]')")

    if tc["cuda_available"]:
        print(f"[PASS] CUDA Available      : TRUE (CUDA Runtime: {tc['cuda_version']})")
        print(f"       GPU Device Count   : {tc['device_count']}")
        for dev in tc["devices"]:
            print(f"       - GPU {dev['id']}: {dev['name']} ({dev['total_memory_gb']} GB VRAM)")
    else:
        print("[INFO] CUDA Available      : FALSE (CPU mode active)")

    # System Resources
    res_info = res["resources"]
    ram_str = f"{res_info['ram_available_gb']} GB avail / {res_info['ram_total_gb']} GB total" if res_info['ram_total_gb'] else "N/A"
    disk_str = f"{res_info['disk_free_gb']} GB free / {res_info['disk_total_gb']} GB total" if res_info['disk_total_gb'] else "N/A"
    print(f"[INFO] System RAM          : {ram_str}")
    print(f"[INFO] Disk Space          : {disk_str}")

    # Git
    git = res["git"]
    if git["is_repo"]:
        dirty_flag = " (dirty)" if git["is_dirty"] else ""
        print(f"[INFO] Git State           : Branch '{git['branch']}', Commit {git['commit']}{dirty_flag}")
    else:
        print("[INFO] Git State           : Not a git repository")

    # Directories
    if res["directory_errors"]:
        print(f"[FAIL] Directory Init      : {len(res['directory_errors'])} errors occurred:")
        for err in res["directory_errors"]:
            print(f"       - {err}")
    else:
        print(f"[PASS] Directory Hierarchy : {res['directories_initialized']} directories verified (read/write OK)")

    # Raw Datasets
    print("\n" + "-" * 65)
    print(" RAW DATASET INVENTORY (data/raw/)")
    print("-" * 65)
    for name, item in res["raw_inventory"].items():
        print(f"  * {name:<12} : {item['status']:<20} ({item['description']})")

    print("=" * 65)
    if res["all_passed"]:
        print(" LAB ENVIRONMENT STATUS: INITIALIZED & READY FOR SYNTHETIC / REAL DATA")
    else:
        print(" LAB ENVIRONMENT STATUS: ISSUES DETECTED (See errors above)")
    print("=" * 65)


if __name__ == "__main__":
    result = run_bootstrap()
    print_report(result)
    sys.exit(0 if result["all_passed"] else 1)
