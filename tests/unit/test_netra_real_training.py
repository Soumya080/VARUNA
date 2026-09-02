"""
Tests for the real NETRA training path (Phase 33).

These are mechanism tests: they prove the loader is manifest-driven, the loss
and metrics are computed rather than hardcoded, the optimizer actually updates
weights, checkpoints round-trip, and the synthetic fallback is unreachable.

Proof that the pipeline works on the *real* corpus is a separate hard gate:
scripts/netra_v02/06_real_smoke_test.py (200 real tiles, 2 real epochs, GPU).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from varuna_netra.dataset.gold import GoldManifestError, NetraGoldDataset
from varuna_netra.training.config import NetraTrainingConfig
from varuna_netra.training.evaluator import NetraEvaluator, SegCounts
from varuna_netra.training.losses import CombinedLoss, DiceLoss, build_loss
from varuna_netra.training.trainer import (
    CudaUnavailableError,
    NetraTrainer,
    parameter_fingerprint,
    resolve_device,
)

TILE = 32  # small tiles keep these tests fast; the loader is size-agnostic


# --------------------------------------------------------------------- #
# fixture: a miniature Gold dataset + manifest with the real structure
# --------------------------------------------------------------------- #
@pytest.fixture
def mini_gold(tmp_path: Path) -> Path:
    rng = np.random.default_rng(0)
    tiles = []
    for split, n, scenes in (("train", 8, ("sceneA", "sceneB")),
                             ("val", 4, ("sceneC",)),
                             ("test", 4, ("sceneD",))):
        d = tmp_path / "data" / "gold" / "netra_v0_2" / split
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            scene = scenes[i % len(scenes)]
            tid = f"{scene}__r{i}c0"
            img = rng.random((2, TILE, TILE)).astype(np.float32)
            msk = np.zeros((TILE, TILE), dtype=np.uint8)
            if i % 2 == 0:                     # half the tiles carry oil
                msk[: TILE // 4, : TILE // 4] = 1
            np.save(d / f"{tid}_img.npy", img)
            np.save(d / f"{tid}_mask.npy", msk)
            tiles.append({
                "tile_id": tid, "scene_id": scene, "source": "zenodo_part1",
                "label_semantics": "OIL_POSITIVE", "split": split,
                "row": i, "col": 0, "pixel_window": [0, i * TILE, TILE, TILE],
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "oil_px": int((msk > 0).sum()), "valid_frac": 1.0,
                "img": f"data/gold/netra_v0_2/{split}/{tid}_img.npy",
                "mask": f"data/gold/netra_v0_2/{split}/{tid}_mask.npy",
            })

    manifest = {
        "dataset_id": "test_mini", "dataset_version": "NETRA-GOLD-v0.2-test",
        "channels": ["VV", "VH"],
        "label_mapping": {"classes": {"0": "NOT_OIL", "1": "OIL"}},
        "tiling": {"tile_size": TILE, "stride": TILE},
        "normalization": {"normalization_version": "test-norm",
                          "channels": {"VV": {"clip_low": -40, "clip_high": -5},
                                       "VH": {"clip_low": -35, "clip_high": -5}}},
        "tiles": tiles,
    }
    mp = tmp_path / "data" / "manifests" / "netra_gold_v0_2.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest))
    return mp


# --------------------------------------------------------------------- #
# dataset: manifest-driven membership
# --------------------------------------------------------------------- #
def test_dataset_is_manifest_driven_and_typed(mini_gold: Path):
    ds = NetraGoldDataset(mini_gold, "train", repo_root=mini_gold.parents[2])
    assert len(ds) == 8
    img, msk = ds[0]
    assert img.shape == (2, TILE, TILE) and img.dtype == torch.float32
    assert msk.shape == (TILE, TILE) and msk.dtype == torch.int64
    assert set(torch.unique(msk).tolist()).issubset({0, 1})


def test_dataset_splits_are_disjoint_by_scene(mini_gold: Path):
    root = mini_gold.parents[2]
    tr = NetraGoldDataset(mini_gold, "train", repo_root=root)
    va = NetraGoldDataset(mini_gold, "val", repo_root=root)
    te = NetraGoldDataset(mini_gold, "test", repo_root=root)
    assert not set(tr.scene_ids) & set(va.scene_ids)
    assert not set(tr.scene_ids) & set(te.scene_ids)
    assert not set(va.scene_ids) & set(te.scene_ids)


def test_unmanifested_files_are_invisible(mini_gold: Path):
    """A stale tile on disk must not become training data."""
    root = mini_gold.parents[2]
    stray_dir = root / "data" / "gold" / "netra_v0_2" / "train"
    np.save(stray_dir / "STALE__r9c9_img.npy", np.zeros((2, TILE, TILE), np.float32))
    np.save(stray_dir / "STALE__r9c9_mask.npy", np.zeros((TILE, TILE), np.uint8))

    ds = NetraGoldDataset(mini_gold, "train", repo_root=root)
    assert len(ds) == 8, "loader picked up an unmanifested file"
    assert not any("STALE" in t for t in ds.tile_ids)
    assert len(list(stray_dir.glob("*.npy"))) == 8 * 2 + 2, "stale files must remain on disk"


def test_missing_manifest_fails_loudly_without_fallback(tmp_path: Path):
    with pytest.raises(GoldManifestError) as exc:
        NetraGoldDataset(tmp_path / "nope.json", "train")
    assert "refusing to substitute" in str(exc.value)


def test_manifest_channel_and_class_contract_is_enforced(mini_gold: Path):
    man = json.loads(mini_gold.read_text())
    man["channels"] = ["VV", "VH", "WIND"]
    mini_gold.write_text(json.dumps(man))
    with pytest.raises(GoldManifestError, match="expects 2"):
        NetraGoldDataset(mini_gold, "train", repo_root=mini_gold.parents[2])


def test_sampling_policy_does_not_change_membership(mini_gold: Path):
    ds = NetraGoldDataset(mini_gold, "train", repo_root=mini_gold.parents[2])
    w = ds.sampler_weights(positive_weight=5.0)
    assert len(w) == len(ds)
    assert w[ds.oil_positive_flags()].min() == 5.0
    assert w[~ds.oil_positive_flags()].max() == 1.0


# --------------------------------------------------------------------- #
# losses: computed, not constant
# --------------------------------------------------------------------- #
def test_dice_loss_is_not_a_constant():
    tgt = torch.zeros(2, 8, 8, dtype=torch.long)
    tgt[:, :4, :4] = 1
    perfect = torch.full((2, 2, 8, 8), -10.0)
    perfect[:, 1][tgt == 1] = 10.0
    perfect[:, 0][tgt == 0] = 10.0
    wrong = torch.full((2, 2, 8, 8), -10.0)
    wrong[:, 0] = 10.0

    d = DiceLoss()
    good, bad = d(perfect, tgt).item(), d(wrong, tgt).item()
    assert good < 0.05, f"perfect prediction should give ~0 Dice loss, got {good}"
    assert bad > 0.9, f"all-background prediction should give ~1 Dice loss, got {bad}"
    assert good != 0.5 and bad != 0.5, "stub constant 0.5 returned"


def test_combined_loss_responds_to_prediction_quality():
    tgt = torch.zeros(2, 8, 8, dtype=torch.long)
    tgt[:, :4, :4] = 1
    loss = CombinedLoss(class_weights=[1.0, 10.0])
    good = torch.full((2, 2, 8, 8), -5.0)
    good[:, 1][tgt == 1] = 5.0
    good[:, 0][tgt == 0] = 5.0
    bad = -good
    assert loss(good, tgt).item() < loss(bad, tgt).item()


def test_loss_is_differentiable():
    logits = torch.randn(2, 2, 8, 8, requires_grad=True)
    tgt = torch.randint(0, 2, (2, 8, 8))
    build_loss("dice_ce", class_weights=[1.0, 10.0])(logits, tgt).backward()
    assert logits.grad is not None and torch.isfinite(logits.grad).all()
    assert logits.grad.abs().sum() > 0


# --------------------------------------------------------------------- #
# evaluator: arithmetic is correct and prediction-sensitive
# --------------------------------------------------------------------- #
def test_segcounts_arithmetic_matches_definitions():
    c = SegCounts()
    c.add(tp=30, fp=10, fn=20, tn=940, n_tiles=1)
    m = c.metrics()
    assert m["iou_oil"] == pytest.approx(30 / 60)
    assert m["dice_oil"] == pytest.approx(60 / 90)
    assert m["precision_oil"] == pytest.approx(30 / 40)
    assert m["recall_oil"] == pytest.approx(30 / 50)
    assert m["f1_oil"] == pytest.approx(2 * 0.75 * 0.6 / 1.35)


def test_evaluator_output_changes_when_predictions_change(mini_gold: Path):
    """The v0.1 stub returned iou_oil=0.75 for any model. This must not."""
    from torch.utils.data import DataLoader

    ds = NetraGoldDataset(mini_gold, "val", repo_root=mini_gold.parents[2])
    loader = DataLoader(ds, batch_size=2)

    class AlwaysOil(torch.nn.Module):
        def forward(self, x):
            out = torch.zeros(x.shape[0], 2, x.shape[2], x.shape[3])
            out[:, 1] = 10.0
            return out

    class AlwaysBackground(torch.nn.Module):
        def forward(self, x):
            out = torch.zeros(x.shape[0], 2, x.shape[2], x.shape[3])
            out[:, 0] = 10.0
            return out

    ev = NetraEvaluator(amp=False)
    a = ev.evaluate(AlwaysOil(), loader, device="cpu")
    b = ev.evaluate(AlwaysBackground(), loader, device="cpu")

    assert a.overall["recall_oil"] == pytest.approx(1.0)
    assert b.overall["recall_oil"] == pytest.approx(0.0)
    assert a.overall["iou_oil"] != b.overall["iou_oil"]
    for m in (a, b):
        assert m.overall["iou_oil"] != 0.75, "hardcoded stub value returned"
        assert m.overall["f1_oil"] != 0.82, "hardcoded stub value returned"


def test_evaluator_breaks_out_populations(mini_gold: Path):
    from torch.utils.data import DataLoader

    ds = NetraGoldDataset(mini_gold, "val", repo_root=mini_gold.parents[2], return_meta=True)

    def collate(b):
        return (torch.stack([x[0] for x in b]), torch.stack([x[1] for x in b]),
                {k: [x[2][k] for x in b] for k in b[0][2]})

    loader = DataLoader(ds, batch_size=2, collate_fn=collate)

    class Zeros(torch.nn.Module):
        def forward(self, x):
            return torch.zeros(x.shape[0], 2, x.shape[2], x.shape[3])

    m = NetraEvaluator(amp=False).evaluate(Zeros(), loader, device="cpu")
    assert set(m.by_population) == {"positive_tiles", "empty_tiles"}
    assert "zenodo_part1" in m.by_source
    assert m.by_population["positive_tiles"]["n_tiles"] + \
           m.by_population["empty_tiles"]["n_tiles"] == len(ds)


# --------------------------------------------------------------------- #
# trainer: real optimizer step, checkpoint round-trip
# --------------------------------------------------------------------- #
def test_resolve_device_fails_loudly_when_cuda_missing(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(CudaUnavailableError) as exc:
        resolve_device("cuda")
    assert "Refusing to silently train on CPU" in str(exc.value)
    assert resolve_device("auto").type == "cpu"   # 'auto' may legitimately downgrade


def test_trainer_updates_weights_and_writes_a_real_checkpoint(mini_gold: Path, tmp_path: Path):
    import segmentation_models_pytorch as smp
    from torch.utils.data import DataLoader

    root = mini_gold.parents[2]
    tr = NetraGoldDataset(mini_gold, "train", repo_root=root)
    va = NetraGoldDataset(mini_gold, "val", repo_root=root)
    train_loader = DataLoader(tr, batch_size=2, shuffle=True)
    val_loader = DataLoader(va, batch_size=2)

    model = smp.Unet("resnet18", encoder_weights=None, in_channels=2, classes=2)
    before = parameter_fingerprint(model)

    cfg = NetraTrainingConfig(epochs=1, batch_size=2, lr=1e-3, warmup_epochs=0,
                              patience=0, amp=False, seed=42,
                              checkpoint_dir=str(tmp_path / "ck"))
    trainer = NetraTrainer(cfg, device="cpu", loss_name="dice_ce",
                           class_weights=[1.0, 10.0], log_interval=0,
                           provenance={"dataset_version": tr.dataset_version,
                                       "manifest_hash": tr.manifest_hash,
                                       "normalization_version": "test-norm"})
    res = trainer.train(model, train_loader, val_loader, "unit_exp", epochs=1)

    assert res.weights_changed, "optimizer did not change any weight"
    assert res.fingerprint_before == before
    assert res.fingerprint_after != before
    assert len(res.history) == 1
    h = res.history[0]
    assert np.isfinite(h["train_loss"]) and h["train_loss"] > 0
    assert h["train_loss"] != 0.45, "hardcoded 0.45/sqrt(epoch) loss returned"

    ck = torch.load(res.best_checkpoint, map_location="cpu", weights_only=False)
    for key in ("model_state_dict", "optimizer_state_dict", "scheduler_state_dict",
                "epoch", "best_metric", "config", "dataset_version",
                "manifest_hash", "normalization_version", "seed"):
        assert key in ck, f"checkpoint missing {key}"
    assert ck["dataset_version"] == tr.dataset_version

    fresh = smp.Unet("resnet18", encoder_weights=None, in_channels=2, classes=2)
    fresh.load_state_dict(ck["model_state_dict"])
    fresh.eval()
    with torch.no_grad():
        out = fresh(torch.randn(1, 2, TILE, TILE))
    assert out.shape == (1, 2, TILE, TILE)
    assert torch.isfinite(out).all()


def test_trainer_supports_resume(mini_gold: Path, tmp_path: Path):
    import segmentation_models_pytorch as smp
    from torch.utils.data import DataLoader

    root = mini_gold.parents[2]
    train_loader = DataLoader(NetraGoldDataset(mini_gold, "train", repo_root=root), batch_size=2)
    val_loader = DataLoader(NetraGoldDataset(mini_gold, "val", repo_root=root), batch_size=2)
    model = smp.Unet("resnet18", encoder_weights=None, in_channels=2, classes=2)
    cfg = NetraTrainingConfig(epochs=1, batch_size=2, warmup_epochs=0, patience=0,
                              amp=False, checkpoint_dir=str(tmp_path / "ck"))
    trainer = NetraTrainer(cfg, device="cpu", log_interval=0)
    r1 = trainer.train(model, train_loader, val_loader, "resume_exp", epochs=1)
    r2 = trainer.train(model, train_loader, val_loader, "resume_exp", epochs=2,
                       resume_from=r1.last_checkpoint)
    assert len(r2.history) >= 1
    ck = torch.load(r2.last_checkpoint, map_location="cpu", weights_only=False)
    assert ck["epoch"] == 2


# --------------------------------------------------------------------- #
# hard safety gate: no synthetic fallback reachable from the entrypoint
# --------------------------------------------------------------------- #
def test_real_entrypoint_has_no_synthetic_fallback():
    repo = Path(__file__).resolve().parents[2]
    src = (repo / "train_netra.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in src.splitlines()
        if not line.strip().startswith("#")
    )
    body = code.split('"""', 2)[-1]          # drop the module docstring
    assert "SyntheticNetraDataset" not in body, \
        "train_netra.py can still reach the synthetic dataset"
    assert "from varuna_netra.dataset.synthetic" not in body
    assert "NetraGoldDataset" in body, "train_netra.py must load Gold via the manifest"
    assert "glob(" not in body, "train_netra.py must not glob for training membership"


def test_real_entrypoint_refuses_missing_manifest(tmp_path, monkeypatch, capsys):
    """With no Gold manifest the entrypoint exits non-zero instead of synthesising."""
    import train_netra as tn

    cfg = {"device": "cpu", "gold_manifest": str(tmp_path / "absent.json"),
           "in_channels": 2, "classes": 2}
    monkeypatch.setattr(tn, "load_config", lambda p: cfg)
    monkeypatch.setattr("sys.argv", ["train_netra.py", "--config", "x.yaml"])
    rc = tn.main()
    assert rc == 2
    out = capsys.readouterr().out
    assert "will not substitute synthetic data" in out
