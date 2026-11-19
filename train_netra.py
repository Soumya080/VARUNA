"""
VARUNA GRID v2 - NETRA real-data training entrypoint.

This file previously detected the Gold tiles, printed that it was using them,
and then trained on `SyntheticNetraDataset` while emitting per-epoch losses from
the closed form `0.45 / sqrt(epoch)`. That path is gone. There is no synthetic
fallback here and no fabricated metric.

Hard guarantees:
  * data membership comes from a versioned Gold manifest, never a directory glob
  * a missing manifest is a fatal error - no substitute data is synthesised
  * `device: cuda` with CUDA unavailable raises rather than falling back to CPU
  * every logged number is measured from real predictions on real tiles

Usage:
    .venv/Scripts/python.exe train_netra.py --config configs/lab/netra.yaml
    .venv/Scripts/python.exe train_netra.py --config configs/lab/netra.yaml --epochs 2
    .venv/Scripts/python.exe train_netra.py --config configs/lab/netra.yaml --resume auto
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
for _p in (REPO_ROOT, REPO_ROOT / "packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np                                                        # noqa: E402
import torch                                                              # noqa: E402
from torch.utils.data import DataLoader, WeightedRandomSampler            # noqa: E402

from varuna_netra.dataset.gold import NetraGoldDataset, manifest_sha256   # noqa: E402
from varuna_netra.model.config import NetraModelConfig                    # noqa: E402
from varuna_netra.model.factory import create_netra_model                 # noqa: E402
from varuna_netra.training.config import NetraTrainingConfig              # noqa: E402
from varuna_netra.training.evaluator import NetraEvaluator                # noqa: E402
from varuna_netra.training.trainer import NetraTrainer, resolve_device    # noqa: E402

SCIENTIFIC_STATUS = "EXPERIMENTAL / UNVALIDATED"


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def load_config(path: Path) -> dict:
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def collate_with_meta(batch):
    imgs = torch.stack([b[0] for b in batch])
    msks = torch.stack([b[1] for b in batch])
    meta = {k: [b[2][k] for b in batch] for k in batch[0][2]}
    return imgs, msks, meta


def build_loaders(cfg: dict, manifest: Path, epochs_limit: int | None = None):
    bs = int(cfg.get("batch_size", 16))
    nw = int(cfg.get("num_workers", 8))
    # Both loaders' worker pools spawn concurrently once persistent_workers=True on
    # both: train's pool stays alive across the whole run, and val's pool spawns on
    # top of it at the end of every epoch. Each worker process reloads torch+CUDA,
    # and on this machine nw=8 + nw=8 = 16 concurrent DLL loads exhausted the
    # Windows paging file mid-epoch-1 (WinError 1455) and stalled the run.
    # Val runs briefly once per epoch and needs far less throughput than train, so
    # it gets a capped, non-persistent pool instead of a matching one.
    val_nw = min(nw, int(cfg.get("val_num_workers", 2)))
    tile_limit = cfg.get("tile_limit")
    # 2026-08-29 incident (part 2): a train loader persistent for the whole run
    # exhausted the Windows paging file at epoch 15 (WinError-class OpenBLAS
    # allocation failure), consistent with a slow per-epoch accumulation. Tried
    # making train workers non-persistent (respawn every epoch) as the fix --
    # that instead triggered a hard native crash (c0000005 access violation in
    # c10.dll, confirmed via Windows Event Log WER records) almost immediately
    # after the respawned pool started, i.e. spawning 8 fresh worker processes
    # every single epoch is itself unstable on this machine's torch/CUDA/driver
    # stack. Reverted: train workers are persistent again (proven stable for 14
    # real epochs before the paging-file incident). Re-verify via
    # 06_real_smoke_test.py before trusting any further change here.

    train_ds = NetraGoldDataset(manifest, "train", repo_root=REPO_ROOT,
                                limit=tile_limit, return_meta=True)
    val_ds = NetraGoldDataset(manifest, "val", repo_root=REPO_ROOT,
                              limit=cfg.get("val_tile_limit"), return_meta=True)

    sampler = None
    shuffle = True
    if cfg.get("positive_aware_sampling", False):
        w = train_ds.sampler_weights(float(cfg.get("positive_weight", 3.0)))
        sampler = WeightedRandomSampler(w.tolist(), num_samples=len(w), replacement=True)
        shuffle = False
        print(f"[SAMPLING] positive-aware sampler active "
              f"(positive_weight={cfg.get('positive_weight', 3.0)}); "
              f"dataset membership unchanged, {len(train_ds)} tiles remain addressable")

    pin = bool(cfg.get("pin_memory", True))
    train_loader = DataLoader(train_ds, batch_size=bs, shuffle=shuffle,
                              sampler=sampler, drop_last=False,
                              num_workers=nw, pin_memory=pin,
                              persistent_workers=nw > 0, collate_fn=collate_with_meta)
    val_loader = DataLoader(val_ds, batch_size=bs, shuffle=False,
                            num_workers=val_nw, pin_memory=pin,
                            persistent_workers=False, collate_fn=collate_with_meta)
    print(f"[LOADERS] train_num_workers={nw} (persistent)  val_num_workers={val_nw} (non-persistent)")
    return train_ds, val_ds, train_loader, val_loader


def main() -> int:
    ap = argparse.ArgumentParser(description="VARUNA NETRA real-data training")
    ap.add_argument("--config", default="configs/lab/netra.yaml")
    ap.add_argument("--epochs", type=int, default=None, help="override config epochs")
    ap.add_argument("--experiment-id", default=None)
    ap.add_argument("--resume", default=None, help="checkpoint path, or 'auto' for <exp>_last.pt")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    started = datetime.now(timezone.utc)
    commit = git_commit()
    config_hash = hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    experiment_id = args.experiment_id or (
        f"netra_{cfg.get('experiment_name', 'baseline')}_{config_hash}"
    )

    print("=" * 74)
    print(f" VARUNA GRID v2 - NETRA TRAINING  [{experiment_id}]")
    print(f" Scientific status: {SCIENTIFIC_STATUS}")
    print("=" * 74)

    # ---- device: fail loudly, never downgrade silently ---- #
    requested = str(cfg.get("device", "cuda"))
    device = resolve_device(requested)   # raises CudaUnavailableError if cuda missing
    print(f"[DEVICE] requested={requested} -> {device}")
    if device.type == "cuda":
        p = torch.cuda.get_device_properties(0)
        free, _ = torch.cuda.mem_get_info()
        print(f"[DEVICE] {p.name} | VRAM {p.total_memory / 1024 ** 3:.1f} GB "
              f"({free / 1024 ** 3:.2f} GB free) | torch {torch.__version__} "
              f"| CUDA {torch.version.cuda}")

    # ---- data: manifest only, no fallback ---- #
    manifest = REPO_ROOT / cfg.get("gold_manifest", "data/manifests/netra_gold_v0_2.json")
    if not manifest.exists():
        print(f"[FATAL] Gold manifest not found: {manifest}")
        print("        Real training requires a real Gold dataset. This entrypoint will "
              "not substitute synthetic data. Build it with scripts/netra_v02/*.py first.")
        return 2

    train_ds, val_ds, train_loader, val_loader = build_loaders(cfg, manifest)
    man_hash = manifest_sha256(manifest)
    print(f"[DATA] manifest        : {manifest.name}  sha256={man_hash[:16]}...")
    print(f"[DATA] dataset_version : {train_ds.dataset_version}")
    print(f"[DATA] normalization   : {train_ds.normalization['normalization_version']}")
    for name, ds in (("train", train_ds), ("val", val_ds)):
        d = ds.describe()
        print(f"[DATA] {name:5s}: {d['n_tiles']} tiles / {d['n_scenes']} scenes | "
              f"pos={d['n_positive_tiles']} empty={d['n_empty_tiles']} | "
              f"oil px {d['oil_pixel_frac']:.4%} | {d['tiles_by_source']}")
    overlap = set(train_ds.scene_ids) & set(val_ds.scene_ids)
    if overlap:
        print(f"[FATAL] {len(overlap)} scenes appear in both train and val")
        return 3
    print(f"[DATA] train/val scene overlap : 0  (verified at load time)")

    # ---- model ---- #
    in_ch = int(cfg.get("in_channels", 2))
    n_cls = int(cfg.get("classes", 2))
    if in_ch != 2 or n_cls != 2:
        print(f"[FATAL] NETRA baseline is 2-channel (VV,VH) / 2-class (NOT_OIL,OIL); "
              f"config asks for in_channels={in_ch}, classes={n_cls}")
        return 4
    model_cfg = NetraModelConfig(
        encoder_name=str(cfg.get("encoder_name", "resnet34")),
        encoder_weights=cfg.get("encoder_weights"),
        in_channels=in_ch, classes=n_cls, tile_confidence_head=True,
    )
    model = create_netra_model(model_cfg)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[MODEL] U-Net {model_cfg.encoder_name} | in_ch={in_ch} classes={n_cls} | "
          f"{n_params / 1e6:.2f} M params | encoder_weights={model_cfg.encoder_weights}")

    # ---- trainer ---- #
    epochs = int(args.epochs if args.epochs is not None else cfg.get("epochs", 50))
    ckpt_dir = REPO_ROOT / cfg.get("checkpoint_dir", "artifacts/checkpoints/netra_v0_2")
    train_cfg = NetraTrainingConfig(
        epochs=epochs,
        batch_size=int(cfg.get("batch_size", 16)),
        lr=float(cfg.get("learning_rate", 3e-4)),
        weight_decay=float(cfg.get("weight_decay", 1e-4)),
        warmup_epochs=int(cfg.get("warmup_epochs", 3)),
        patience=int(cfg.get("patience", 8)),
        amp=bool(cfg.get("mixed_precision", True)),
        seed=int(cfg.get("seed", 42)),
        checkpoint_dir=str(ckpt_dir),
    )
    exp_dir = REPO_ROOT / "artifacts" / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    log_path = exp_dir / f"{experiment_id}.log.jsonl"

    provenance = {
        "dataset_version": train_ds.dataset_version,
        "manifest_hash": man_hash,
        "normalization_version": train_ds.normalization["normalization_version"],
        "git_commit": commit,
        "config_hash": config_hash,
        "experiment_id": experiment_id,
    }
    trainer = NetraTrainer(
        train_cfg, device=requested,
        loss_name=str(cfg.get("loss", "dice_ce")),
        class_weights=cfg.get("class_weights", [1.0, 10.0]),
        monitor=str(cfg.get("monitor", "iou_oil")),
        provenance=provenance,
        log_interval=int(cfg.get("log_interval", 20)),
    )
    print(f"[TRAIN] epochs={epochs} batch={train_cfg.batch_size} "
          f"lr={train_cfg.lr} amp={train_cfg.amp} loss={cfg.get('loss', 'dice_ce')} "
          f"class_weights={cfg.get('class_weights', [1.0, 10.0])} "
          f"monitor={cfg.get('monitor', 'iou_oil')} patience={train_cfg.patience}")
    print(f"[TRAIN] checkpoints -> {ckpt_dir}")
    print(f"[TRAIN] epoch log   -> {log_path}")

    resume = args.resume
    if resume == "auto":
        cand = ckpt_dir / f"{experiment_id}_last.pt"
        resume = str(cand) if cand.exists() else None
        print(f"[TRAIN] resume auto -> {resume or 'no prior checkpoint, starting fresh'}")

    t0 = time.perf_counter()
    result = trainer.train(model, train_loader, val_loader, experiment_id,
                           epochs=epochs, resume_from=resume, log_path=log_path)

    print("\n" + "=" * 74)
    print(" TRAINING COMPLETE")
    print("=" * 74)
    print(f" epochs run       : {result.epochs_run}")
    print(f" best epoch       : {result.best_epoch}  ({trainer.monitor}={result.best_metric:.6f})")
    print(f" weights changed  : {result.weights_changed}")
    print(f" best checkpoint  : {result.best_checkpoint}")
    print(f" last checkpoint  : {result.last_checkpoint}")
    print(f" peak VRAM        : {result.peak_vram_gb:.2f} GB (MEASURED)")
    print(f" wall clock       : {result.total_seconds / 60:.1f} min (MEASURED)")

    # ---- final validation metrics from the best checkpoint ---- #
    best = torch.load(result.best_checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(best["model_state_dict"])
    evaluator = NetraEvaluator(amp=train_cfg.amp)
    val_metrics = evaluator.evaluate(model, val_loader, device=device, split="val")
    o = val_metrics.overall
    print("\n[VAL METRICS - best checkpoint, computed from real predictions]")
    print(f"  IoU(oil)={o['iou_oil']:.4f}  Dice={o['dice_oil']:.4f}  "
          f"P={o['precision_oil']:.4f}  R={o['recall_oil']:.4f}  F1={o['f1_oil']:.4f}")
    print(f"  PR-AUC={val_metrics.pr_auc:.4f}  best-F1={val_metrics.best_f1:.4f} "
          f"@thr={val_metrics.best_f1_threshold:.3f}")
    for src, m in val_metrics.by_source.items():
        print(f"  [{src}] tiles={m['n_tiles']} FP-pixel-rate={m['fp_pixel_rate']:.6f} "
              f"IoU={m['iou_oil']:.4f}")

    metadata = {
        "experiment_id": experiment_id,
        "model_name": "netra",
        "scientific_status": SCIENTIFIC_STATUS,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "config_hash": config_hash,
        "config": cfg,
        "seed": train_cfg.seed,
        "dataset": {
            "manifest": str(manifest.relative_to(REPO_ROOT)),
            "manifest_hash": man_hash,
            "dataset_version": train_ds.dataset_version,
            "normalization_version": train_ds.normalization["normalization_version"],
            "train": train_ds.describe(),
            "val": val_ds.describe(),
        },
        "model": {"architecture": "unet", "encoder": model_cfg.encoder_name,
                  "in_channels": in_ch, "classes": n_cls, "parameters": n_params,
                  "encoder_weights": model_cfg.encoder_weights},
        "hardware": {
            "device": str(result.device),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "torch": torch.__version__, "cuda": torch.version.cuda,
            "peak_vram_gb": result.peak_vram_gb, "amp": train_cfg.amp,
            "measurement": "MEASURED",
        },
        "training": {
            "epochs_requested": epochs, "epochs_run": result.epochs_run,
            "best_epoch": result.best_epoch, "monitor": trainer.monitor,
            "best_metric": result.best_metric,
            "weights_changed": result.weights_changed,
            "fingerprint_before": result.fingerprint_before,
            "fingerprint_after": result.fingerprint_after,
            "wall_clock_s": result.total_seconds,
            "history": result.history,
        },
        "val_metrics": val_metrics.to_dict(),
        "checkpoints": {"best": result.best_checkpoint, "last": result.last_checkpoint},
        "note": (
            "Metrics above are computed from real model predictions on real held-out "
            "Gold tiles. Test-split evaluation is deliberately NOT run here; it is run "
            "once, separately, after the training configuration is frozen."
        ),
    }
    (exp_dir / f"{experiment_id}.json").write_text(json.dumps(metadata, indent=2, default=str))
    print(f"\n[EXPERIMENT] {exp_dir / (experiment_id + '.json')}")
    print(f"[STATUS] {SCIENTIFIC_STATUS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
