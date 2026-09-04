"""M8 fix (docs/product/HONESTY_LEDGER.md #10).

The original test passed `list[NetraSample]` — pydantic models holding
*paths*, no tensor data — directly to `NetraTrainer.train()`, which iterates
its `train_loader` argument expecting `(images, masks)` tensor batches (see
`trainer.py`'s `for step, batch in enumerate(train_loader): images, masks =
batch[0], batch[1]`). This never actually exercised training; it failed on
the first batch with `TypeError: 'NetraSample' object is not subscriptable`.

Real fix: wrap the sample list in a `torch.utils.data.Dataset` that actually
loads each sample's `.npy` tile/mask off disk into tensors — the same shape
of adapter `NetraGoldDataset` (packages/varuna_netra/dataset/gold.py) is for
real Gold tiles — then hand a `DataLoader` over that Dataset to the trainer,
which is what it was always designed to consume.
"""
import numpy as np
import os
import pytest
import torch
from torch.utils.data import DataLoader, Dataset

from varuna_netra.model.config import NetraModelConfig
from varuna_netra.model.factory import create_netra_model
from varuna_netra.training.config import NetraTrainingConfig
from varuna_netra.training.trainer import NetraTrainer
from varuna_netra.dataset.synthetic import SyntheticNetraDataset
from varuna_netra.dataset.schema import NetraSample


class _SyntheticTensorDataset(Dataset):
    """Adapts a `list[NetraSample]` (paths + metadata) into the
    `(image_tensor, mask_tensor)` contract `NetraTrainer.train()` actually
    requires — reading each sample's `.npy` tile/mask off disk, the same
    role `NetraGoldDataset.__getitem__` plays for real Gold tiles."""

    def __init__(self, samples: list[NetraSample]):
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        s = self.samples[idx]
        image = torch.from_numpy(np.load(s.tile_path).astype(np.float32))
        mask = torch.from_numpy(np.load(s.mask_path).astype(np.int64))
        return image, mask


def test_netra_training_loop(tmp_path):
    # SyntheticNetraDataset writes real (3, 512, 512) image / (512, 512)
    # mask .npy files to a temp dir per sample — see its own module. Closed
    # explicitly in `finally` rather than relying only on its __del__/atexit
    # backstop, so this test doesn't leave its ~150MB behind even on a
    # failure.
    dataset = SyntheticNetraDataset(num_samples=10, seed=42)
    try:
        train_loader = DataLoader(
            _SyntheticTensorDataset(dataset.list_samples(split="train")),
            batch_size=2, shuffle=True,
        )
        val_loader = DataLoader(
            _SyntheticTensorDataset(dataset.list_samples(split="val")),
            batch_size=2, shuffle=False,
        )

        # 3 channels (VV, VH, wind) to match SyntheticNetraDataset's
        # generated tiles; 3 classes (bg/oil/lookalike) to match its
        # generated masks.
        model_config = NetraModelConfig(encoder_name="resnet18", classes=3, in_channels=3)
        model = create_netra_model(model_config)

        checkpoint_dir = str(tmp_path / "models")
        train_config = NetraTrainingConfig(
            epochs=2,
            batch_size=2,
            checkpoint_dir=checkpoint_dir,
            seed=42,
        )
        trainer = NetraTrainer(train_config)

        experiment_id = "test_exp_123"
        result = trainer.train(model, train_loader, val_loader, experiment_id)
        best_ckpt = result.best_checkpoint if hasattr(result, "best_checkpoint") else result

        assert os.path.exists(best_ckpt)
    finally:
        dataset.close()
    assert best_ckpt.endswith(f"{experiment_id}_best.pt")


def test_trainer_batch_contract_with_a_minimal_synthetic_dataset(tmp_path):
    """The test with lasting value, per the plan this fix comes from: even
    if gold/synthetic tile generation ever breaks, this pins the actual
    contract `NetraTrainer.train()` requires from its `train_loader` /
    `val_loader` arguments — a `Dataset` yielding `(image[C,H,W],
    mask[H,W])` tensor pairs — using nothing but in-memory random tensors,
    no disk I/O at all."""

    class _TinyDataset(Dataset):
        def __init__(self, n: int, channels: int, size: int, classes: int):
            self.n, self.channels, self.size, self.classes = n, channels, size, classes

        def __len__(self):
            return self.n

        def __getitem__(self, idx: int):
            image = torch.randn(self.channels, self.size, self.size)
            mask = torch.randint(0, self.classes, (self.size, self.size), dtype=torch.long)
            return image, mask

    train_loader = DataLoader(_TinyDataset(4, channels=2, size=32, classes=2), batch_size=2)
    val_loader = DataLoader(_TinyDataset(2, channels=2, size=32, classes=2), batch_size=2)

    model_config = NetraModelConfig(encoder_name="resnet18", classes=2, in_channels=2)
    model = create_netra_model(model_config)

    # `tmp_path` (pytest's own fixture), not a manual `TemporaryDirectory`:
    # torch's checkpoint file can still hold an open handle when a manual
    # context manager tries to remove its directory on Windows, raising
    # `PermissionError` on cleanup. `tmp_path` is removed by pytest itself,
    # later and more tolerantly.
    ckpt_dir = str(tmp_path / "models")
    train_config = NetraTrainingConfig(epochs=1, batch_size=2, checkpoint_dir=ckpt_dir, seed=1)
    trainer = NetraTrainer(train_config)
    result = trainer.train(model, train_loader, val_loader, "tiny_contract_test")
    best_ckpt = result.best_checkpoint if hasattr(result, "best_checkpoint") else result
    assert os.path.exists(best_ckpt)
