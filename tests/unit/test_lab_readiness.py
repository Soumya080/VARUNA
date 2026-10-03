"""
VARUNA GRID v2 — Laboratory Training Readiness Unit & Integration Tests.

Verifies:
- Lab bootstrap execution, directory creation, permission checks
- Missing dataset graceful handling (reported as 'NOT PROVIDED' without error)
- GPU and CUDA diagnostics (graceful fallback and accurate reporting)
- Lab status aggregation
- Synthetic smoke test pipeline
- NETRA smoke training, checkpointing, and experiment tracking
- CHHAYA smoke training, checkpointing, and experiment tracking
- Lab YAML configurations validity
- Data pipeline entrypoint functions

All tests run 100% offline and do NOT require CUDA or external downloads.
"""

from __future__ import annotations

import os
import json
import yaml
import pytest
from pathlib import Path

from scripts.lab_bootstrap import (
    run_bootstrap,
    check_python,
    check_package_manager,
    check_torch_and_cuda,
    check_system_resources,
    check_git_state,
    init_and_verify_directories,
    scan_raw_datasets,
    REQUIRED_DIRECTORIES,
)
from scripts.check_gpu import run_gpu_check, check_system_nvidia_smi
from scripts.lab_status import get_lab_status, check_training_configs, check_data_and_artifact_status
from scripts.lab_smoke_test import run_synthetic_smoke_test, create_synthetic_scenes
from scripts.smoke_train_netra import run_netra_smoke_training
from scripts.smoke_train_chhaya import run_chhaya_smoke_training
from scripts.validate_data import validate_data
from scripts.build_canonical import build_canonical_datasets
from scripts.build_manifest import build_manifest_file
from scripts.build_gold import build_gold_dataset
import train_netra as train_netra_module
from train_chhaya import train_chhaya


def test_check_python():
    info = check_python()
    assert info["compatible"] is True
    assert info["version"] is not None
    assert Path(info["executable"]).exists()


def test_check_package_manager():
    pm = check_package_manager()
    assert "uv" in pm or "pip" in pm


def test_check_torch_and_cuda():
    tc = check_torch_and_cuda()
    assert "torch_installed" in tc
    assert "cuda_available" in tc
    assert isinstance(tc["cuda_available"], bool)


def test_init_and_verify_directories(tmp_path):
    created, errors = init_and_verify_directories(tmp_path)
    assert len(errors) == 0
    assert len(created) == len(REQUIRED_DIRECTORIES)
    for rel_path in REQUIRED_DIRECTORIES:
        d = tmp_path / rel_path
        assert d.exists()
        assert (d / ".gitkeep").exists()


def test_scan_raw_datasets_empty_handling(tmp_path):
    # Initialize empty dirs
    init_and_verify_directories(tmp_path)
    inv = scan_raw_datasets(tmp_path)
    assert len(inv) > 0
    for name, data in inv.items():
        assert data["status"] == "NOT PROVIDED"
        assert data["file_count"] == 0


def test_run_bootstrap(tmp_path):
    res = run_bootstrap(tmp_path)
    assert res["all_passed"] is True
    assert res["directories_initialized"] == len(REQUIRED_DIRECTORIES)
    assert len(res["directory_errors"]) == 0
    assert res["python"]["compatible"] is True


def test_check_gpu():
    diag = run_gpu_check()
    assert "training_ready" in diag
    assert isinstance(diag["training_ready"], bool)
    if not diag["cuda_available"]:
        assert diag["training_ready"] is False


def test_lab_status(tmp_path):
    init_and_verify_directories(tmp_path)
    status = get_lab_status(tmp_path)
    assert "git" in status
    assert "python" in status
    assert "gpu" in status
    assert "resources" in status
    assert "data_dirs" in status


def test_synthetic_lab_smoke_test():
    res = run_synthetic_smoke_test()
    assert res["all_passed"] is True
    for stage_name, passed in res["stages"].items():
        assert passed is True, f"Stage {stage_name} failed"


def test_smoke_train_netra(tmp_path):
    ckpt_dir = str(tmp_path / "checkpoints" / "netra")
    exp_dir = str(tmp_path / "experiments")

    res = run_netra_smoke_training(
        epochs=2,
        batch_size=2,
        seed=42,
        device="cpu",
        checkpoint_dir=ckpt_dir,
        experiment_dir=exp_dir,
    )
    assert Path(res["checkpoint_path"]).exists()
    assert Path(res["metadata_file"]).exists()
    assert res["model_version"] == "v0.1.0-smoke"

    with open(res["metadata_file"], "r") as f:
        meta = json.load(f)
    assert meta["model_name"] == "netra"
    assert "val_iou_oil" in meta["metrics"]
    assert res["weights_changed"] is True, "smoke run did not update any weight"
    assert meta["scientific_status"].startswith("SYNTHETIC")


def test_smoke_train_chhaya(tmp_path):
    ckpt_dir = str(tmp_path / "checkpoints" / "chhaya")
    exp_dir = str(tmp_path / "experiments")

    res = run_chhaya_smoke_training(
        epochs=2,
        batch_size=4,
        seed=42,
        device="cpu",
        checkpoint_dir=ckpt_dir,
        experiment_dir=exp_dir,
    )
    assert Path(res["checkpoint_path"]).exists()
    assert Path(res["metadata_file"]).exists()
    assert res["model_version"] == "v0.1.0-smoke"

    with open(res["metadata_file"], "r") as f:
        meta = json.load(f)
    assert meta["model_name"] == "chhaya"
    assert "mean_distance_km" in meta["metrics"]


def test_lab_training_configs_exist():
    repo_root = Path(__file__).resolve().parent.parent.parent
    netra_yaml = repo_root / "configs" / "lab" / "netra.yaml"
    chhaya_yaml = repo_root / "configs" / "lab" / "chhaya.yaml"

    assert netra_yaml.exists(), "configs/lab/netra.yaml missing"
    assert chhaya_yaml.exists(), "configs/lab/chhaya.yaml missing"

    with open(netra_yaml, "r") as f:
        n_cfg = yaml.safe_load(f)
    assert "batch_size" in n_cfg
    assert "image_size" in n_cfg
    assert "learning_rate" in n_cfg
    assert "checkpoint_dir" in n_cfg
    assert "mixed_precision" in n_cfg

    with open(chhaya_yaml, "r") as f:
        c_cfg = yaml.safe_load(f)
    assert "batch_size" in c_cfg
    assert "hidden_dim" in c_cfg
    assert "learning_rate" in c_cfg
    assert "checkpoint_dir" in c_cfg


def test_validate_data_script():
    res = validate_data(synthetic=True)
    assert res["valid_count"] > 0


def test_build_canonical_script():
    res = build_canonical_datasets(synthetic=True, n_scenes=3)
    assert res["canonical_count"] == 3


def test_build_manifest_script():
    res = build_manifest_file(dataset_id="test_manifest", version="v1")
    assert res["samples"] > 0
    assert Path(res["manifest_path"]).exists()


def test_build_gold_script():
    res = build_gold_dataset(synthetic=True, tile_size=32)
    assert res["tiles_written"] > 0
    assert res["tracks_written"] > 0


def test_train_netra_refuses_to_run_without_real_gold(tmp_path, monkeypatch, capsys):
    """The real entrypoint must fail loudly rather than fall back to synthetic data.

    This replaces the former `test_train_netra_dry_run`, which asserted that a
    pipeline succeeded while it was in fact training on `SyntheticNetraDataset`
    and printing losses from the closed form `0.45 / sqrt(epoch)`.
    """
    cfg = {
        "device": "cpu",
        "gold_manifest": str(tmp_path / "no_such_manifest.json"),
        "in_channels": 2,
        "classes": 2,
    }
    monkeypatch.setattr(train_netra_module, "load_config", lambda p: cfg)
    monkeypatch.setattr("sys.argv", ["train_netra.py"])
    rc = train_netra_module.main()
    assert rc == 2, "entrypoint must exit non-zero when Gold is absent"
    assert "will not substitute synthetic data" in capsys.readouterr().out


def test_train_netra_entrypoint_has_no_synthetic_path():
    src = (Path(train_netra_module.__file__)).read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]
    assert "SyntheticNetraDataset" not in body
    assert "NetraGoldDataset" in body


def test_train_chhaya_dry_run():
    res = train_chhaya(config_path="configs/lab/chhaya.yaml", dry_run=True)
    assert res["experiment_id"] is not None
    assert Path(res["checkpoint_path"]).exists()
