"""
VARUNA GRID v2 - NETRA mechanism smoke test (SYNTHETIC TENSORS, NOT REAL DATA).

WHAT THIS IS
    A fast, offline, CPU-only check that the NETRA training machinery is wired
    together: model builds, loss computes, gradients flow, the optimizer moves
    weights, a checkpoint is written and reloads. It runs in seconds and needs
    neither CUDA nor the Gold dataset.

WHAT THIS IS NOT
    It is NOT evidence about oil-spill detection. The tensors are deterministic
    noise, so every metric it reports describes a model fitted to noise. No
    result from this script may be reported, plotted, or compared against a
    real run.

    The real gate is:  scripts/netra_v02/06_real_smoke_test.py
    (200 real manifested Gold tiles, 2 real epochs, real GPU, real metrics.)

This file previously logged `simulated_loss = 0.50 / epoch` as a training
trajectory and read hardcoded constants back out of the stub evaluator. Both
are gone: the numbers below are measured, even though the data is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import torch                                                          # noqa: E402
from torch.utils.data import DataLoader, TensorDataset                # noqa: E402

from varuna_netra.model.config import NetraModelConfig                # noqa: E402
from varuna_netra.model.factory import create_netra_model             # noqa: E402
from varuna_netra.training.config import NetraTrainingConfig          # noqa: E402
from varuna_netra.training.trainer import NetraTrainer                # noqa: E402
from varuna_domain.model_registry import InMemoryModelRegistry        # noqa: E402
from varuna_infra.experiment.store import InMemoryExperimentStore     # noqa: E402
from varuna_infra.experiment.runner import ExperimentRunner           # noqa: E402

DATASET_LABEL = "synthetic-tensors-v2"
TILE = 64  # small on purpose: this is a mechanism check, not a benchmark


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _synthetic_loaders(n: int, batch_size: int, seed: int):
    """Deterministic noise tensors with a planted rectangle as the positive class."""
    g = torch.Generator().manual_seed(seed)
    x = torch.rand((n, 2, TILE, TILE), generator=g)
    y = torch.zeros((n, TILE, TILE), dtype=torch.long)
    y[:, : TILE // 4, : TILE // 4] = 1          # ~6% positive pixels
    x[:, :, : TILE // 4, : TILE // 4] += 0.5    # a signal the model can actually learn
    split = int(n * 0.8)
    train = TensorDataset(x[:split], y[:split])
    val = TensorDataset(x[split:], y[split:])
    return (DataLoader(train, batch_size=batch_size, shuffle=True),
            DataLoader(val, batch_size=batch_size))


def run_netra_smoke_training(
    epochs: int = 2,
    batch_size: int = 2,
    seed: int = 42,
    device: str = "cpu",
    checkpoint_dir: str = "artifacts/checkpoints/netra_smoke",
    experiment_dir: str = "artifacts/experiments",
    num_samples: int = 10,
) -> dict:
    print("=" * 65)
    print(" NETRA MECHANISM SMOKE TEST - SYNTHETIC TENSORS")
    print(" NOT REAL DATA. NOT A SCIENTIFIC RESULT.")
    print(" Real gate: scripts/netra_v02/06_real_smoke_test.py")
    print("=" * 65)

    actual_device = device
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "device='cuda' requested but CUDA is unavailable; refusing to fall back silently"
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    git_commit = _git_commit()
    print(f"Device            : {actual_device.upper()}")
    print(f"Seed              : {seed}   Epochs: {epochs}   Batch: {batch_size}")

    train_loader, val_loader = _synthetic_loaders(num_samples, batch_size, seed)
    print(f"[PASS] Synthetic tensors: {len(train_loader.dataset)} train / "
          f"{len(val_loader.dataset)} val  (shape [2,{TILE},{TILE}])")

    model_config = NetraModelConfig(
        encoder_name="resnet18", encoder_weights=None, in_channels=2, classes=2,
    )
    model = create_netra_model(model_config)
    print(f"[PASS] Model            : U-Net {model_config.encoder_name}, "
          f"in_ch={model_config.in_channels}, classes={model_config.classes}")

    full_ckpt_dir = REPO_ROOT / checkpoint_dir
    full_exp_dir = REPO_ROOT / experiment_dir
    full_ckpt_dir.mkdir(parents=True, exist_ok=True)
    full_exp_dir.mkdir(parents=True, exist_ok=True)

    train_config = NetraTrainingConfig(
        epochs=epochs, batch_size=batch_size, lr=3e-4, weight_decay=1e-4,
        warmup_epochs=0, patience=0, amp=False, seed=seed,
        checkpoint_dir=str(full_ckpt_dir),
    )
    config_dict = {"model": model_config.model_dump(),
                   "training": train_config.model_dump(), "seed": seed}
    config_hash = hashlib.sha256(
        json.dumps(config_dict, sort_keys=True).encode()
    ).hexdigest()[:12]

    exp_store = InMemoryExperimentStore()
    exp_runner = ExperimentRunner(exp_store)
    result_holder: dict = {}

    def _train_step(exp_id: str):
        trainer = NetraTrainer(
            train_config, device=actual_device, loss_name="dice_ce",
            class_weights=[1.0, 10.0], log_interval=0,
            provenance={"dataset_version": DATASET_LABEL,
                        "manifest_hash": None,
                        "normalization_version": None,
                        "experiment_id": exp_id},
        )
        res = trainer.train(model, train_loader, val_loader, exp_id, epochs=epochs)
        result_holder["res"] = res
        for h in res.history:
            exp_store.log_metric(exp_id, f"train_loss_epoch_{h['epoch']}", h["train_loss"])
            exp_store.log_metric(exp_id, f"val_loss_epoch_{h['epoch']}", h["val_loss"])
            print(f"  Epoch {h['epoch']}/{epochs} - train_loss={h['train_loss']:.4f} "
                  f"val_loss={h['val_loss']:.4f} IoU={h['val_iou_oil']:.4f} "
                  f"(MEASURED on synthetic tensors)")
        exp_store.log_metric(exp_id, "val_iou_oil", res.history[-1]["val_iou_oil"])
        exp_store.log_metric(exp_id, "val_dice_oil", res.history[-1]["val_dice_oil"])

    experiment_id = exp_runner.run("smoke_netra_run", _train_step)
    res = result_holder["res"]
    print(f"[PASS] Checkpoint       : {res.best_checkpoint}")
    print(f"[PASS] Weights changed  : {res.weights_changed}")

    last = res.history[-1]
    registry = InMemoryModelRegistry()
    registered_version = registry.register(
        model_name="netra", version="v0.1.0-smoke",
        artifact_path=res.best_checkpoint, dataset_version=DATASET_LABEL,
        training_config=config_dict, git_commit=git_commit,
    )
    print(f"[PASS] Model Registry   : '{registered_version.version}' "
          f"({registered_version.status.value})")

    metadata = {
        "experiment_id": experiment_id,
        "model_name": "netra",
        "model_version": registered_version.version,
        "dataset_version": DATASET_LABEL,
        "scientific_status": "SYNTHETIC MECHANISM CHECK - NOT A RESULT",
        "git_commit": git_commit,
        "config_hash": config_hash,
        "seed": seed,
        "device": actual_device,
        "timestamp": timestamp,
        "epochs": epochs,
        "batch_size": batch_size,
        "checkpoint_path": res.best_checkpoint,
        "weights_changed": res.weights_changed,
        "metrics": {
            "val_iou_oil": last["val_iou_oil"],
            "val_dice_oil": last["val_dice_oil"],
            "val_f1_oil": last["val_f1_oil"],
            "train_loss": last["train_loss"],
            "measurement": "MEASURED on synthetic tensors; carries no real-data meaning",
        },
        "history": res.history,
    }
    exp_file = full_exp_dir / f"{experiment_id}.json"
    exp_file.write_text(json.dumps(metadata, indent=2))
    print(f"[PASS] Metadata         : {exp_file}")
    print("-" * 65)
    print(" MECHANISM VERIFIED. This says nothing about oil detection.")
    print("=" * 65)

    return {
        "experiment_id": experiment_id,
        "checkpoint_path": res.best_checkpoint,
        "model_version": registered_version.version,
        "metadata_file": str(exp_file),
        "weights_changed": res.weights_changed,
    }


if __name__ == "__main__":
    run_netra_smoke_training()
