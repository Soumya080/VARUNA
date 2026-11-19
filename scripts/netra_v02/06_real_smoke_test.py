"""
NETRA-GOLD-v0.2 | Stage 06 - CRITICAL REAL-DATA SMOKE TEST (Phase 24).

HARD GATE. Long baseline training is authorised only if every criterion below
passes. This test uses 200 REAL manifested Gold tiles for 2 REAL epochs on the
REAL GPU with the REAL model, loss, backward pass and optimizer.

It must never touch SyntheticNetraDataset, random labels, hardcoded losses or
hardcoded metrics - and it asserts as much rather than merely asserting it in
a comment.

Acceptance criteria (all must pass):
  1  REAL DATA LOADED         tiles resolve to manifested files on disk
  2  CORRECT SHAPES           [B,2,512,512] image, [B,512,512] mask
  3  GPU ACTUALLY USED        model and batch on cuda, VRAM accounted
  4  REAL LOSS COMPUTED       epoch 1 and epoch 2 losses from real predictions
  5  WEIGHTS ACTUALLY CHANGE  parameter fingerprint differs after training
  6  METRICS NOT CONSTANTS    evaluator output moves when predictions move
  7  CHECKPOINT IS REAL       contains model/optimizer/epoch/config/dataset version
  8  CHECKPOINT RELOAD        fresh model loads it and runs inference
  9  GPU USAGE REPORTED       device, peak VRAM, wall clock
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "packages"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from varuna_netra.dataset.gold import NetraGoldDataset, manifest_sha256   # noqa: E402
from varuna_netra.model.config import NetraModelConfig                    # noqa: E402
from varuna_netra.model.factory import create_netra_model                 # noqa: E402
from varuna_netra.training.config import NetraTrainingConfig              # noqa: E402
from varuna_netra.training.evaluator import NetraEvaluator                # noqa: E402
from varuna_netra.training.trainer import NetraTrainer, parameter_fingerprint  # noqa: E402

MANIFEST = REPO / "data" / "manifests" / "netra_gold_v0_2.json"
OUT = REPO / "reports" / "netra_v02"
CKPT_DIR = REPO / "artifacts" / "checkpoints" / "netra_v0_2_smoke"


class BiasedHead(nn.Module):
    """Wraps a model and shifts the OIL logit. Used only to prove that the
    evaluator responds to prediction changes - never in a training path."""

    def __init__(self, model: nn.Module, oil_bias: float) -> None:
        super().__init__()
        self.model = model
        self.oil_bias = float(oil_bias)

    def forward(self, x):
        logits = self.model(x)
        out = logits.clone()
        out[:, 1] = out[:, 1] + self.oil_bias
        return out


def banner(t: str) -> None:
    print("\n" + "=" * 70)
    print(f" {t}")
    print("=" * 70)


def collate_with_meta(batch):
    """Module-level so Windows spawn-based DataLoader workers can pickle it."""
    imgs = torch.stack([b[0] for b in batch])
    msks = torch.stack([b[1] for b in batch])
    meta = {k: [b[2][k] for b in batch] for k in batch[0][2]}
    return imgs, msks, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", type=int, default=200)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    results: dict[str, bool] = {}
    evidence: dict = {}
    t_start = time.perf_counter()

    banner("VARUNA GRID v2 - NETRA REAL-DATA SMOKE TEST (HARD GATE)")
    print(f"Manifest : {MANIFEST}")
    if not MANIFEST.exists():
        print("[FATAL] Gold manifest absent. Real training requires real Gold; "
              "this test refuses to synthesise a replacement.")
        return 1

    # ---------------- 1. REAL DATA LOADED ---------------- #
    banner("1. REAL DATA LOADED")
    train_ds = NetraGoldDataset(MANIFEST, split="train", repo_root=REPO,
                                limit=args.tiles, limit_seed=args.seed, return_meta=True)
    val_ds = NetraGoldDataset(MANIFEST, split="val", repo_root=REPO,
                              limit=max(32, args.tiles // 4), limit_seed=args.seed,
                              return_meta=True)
    man_hash = manifest_sha256(MANIFEST)
    print(f"dataset_version : {train_ds.dataset_version}")
    print(f"manifest_sha256 : {man_hash}")
    print(f"train tiles     : {len(train_ds)} from {len(train_ds.scene_ids)} scenes")
    print(f"val   tiles     : {len(val_ds)} from {len(val_ds.scene_ids)} scenes")
    print(f"normalization   : {train_ds.normalization['normalization_version']}")
    print(f"label mapping   : {train_ds.label_mapping['classes']}")

    assert type(train_ds).__name__ == "NetraGoldDataset", "not the real Gold dataset class"
    on_disk_ok = all((REPO / t["img"]).exists() and (REPO / t["mask"]).exists()
                     for t in train_ds.tiles)
    print(f"all {len(train_ds)} tiles exist on disk : {on_disk_ok}")

    print("\nsample tiles:")
    for i in range(min(4, len(train_ds))):
        img, msk, meta = train_ds[i]
        print(f"  {meta['tile_id']}")
        print(f"    parent_scene={meta['scene_id']}  source={meta['source']}  split={meta['split']}")
        print(f"    image  shape={tuple(img.shape)} dtype={img.dtype} "
              f"min={img.min():.4f} max={img.max():.4f} mean={img.mean():.4f} std={img.std():.4f}")
        print(f"    mask   shape={tuple(msk.shape)} dtype={msk.dtype} "
              f"uniq={torch.unique(msk).tolist()} oil_px={int((msk > 0).sum())}")
    desc = train_ds.describe()
    print(f"\ntrain subset: {desc['n_positive_tiles']} positive / {desc['n_empty_tiles']} empty, "
          f"oil pixels {desc['oil_pixel_frac']:.4%}, sources {desc['tiles_by_source']}")
    results["DATA"] = on_disk_ok and len(train_ds) > 0
    evidence["data"] = {"manifest_hash": man_hash, "train_tiles": len(train_ds),
                        "val_tiles": len(val_ds), **desc}

    # ---------------- 2. DATALOADER + SHAPES ---------------- #
    banner("2. DATALOADER AND SHAPES")
    # val_num_workers is capped and non-persistent: matching train's persistent
    # pool caused both pools' worker processes to be alive concurrently at
    # end-of-epoch, each reloading torch+CUDA, which exhausted the Windows
    # paging file during the full baseline run (WinError 1455). See train_netra.py.
    val_num_workers = min(args.num_workers, 2)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=args.num_workers, pin_memory=True,
                              persistent_workers=args.num_workers > 0,
                              drop_last=False, collate_fn=collate_with_meta)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=val_num_workers, pin_memory=True,
                            persistent_workers=False, collate_fn=collate_with_meta)

    xb, yb, mb = next(iter(train_loader))
    print(f"image batch : {tuple(xb.shape)} {xb.dtype}")
    print(f"mask  batch : {tuple(yb.shape)} {yb.dtype}")
    shapes_ok = (xb.ndim == 4 and xb.shape[1] == 2 and xb.shape[2:] == (512, 512)
                 and yb.ndim == 3 and yb.shape[1:] == (512, 512) and yb.dtype == torch.int64)
    print(f"shapes correct ([B,2,512,512] / [B,512,512] int64): {shapes_ok}")
    results["DATALOADER"] = shapes_ok
    evidence["shapes"] = {"image": list(xb.shape), "mask": list(yb.shape)}

    # ---------------- 3. GPU ---------------- #
    banner("3. GPU")
    if not torch.cuda.is_available():
        print("[FATAL] CUDA unavailable - refusing to fall back to CPU")
        return 1
    device = torch.device("cuda")
    torch.cuda.reset_peak_memory_stats()
    model_cfg = NetraModelConfig(encoder_name="resnet34", encoder_weights=None,
                                 in_channels=2, classes=2)
    model = create_netra_model(model_cfg).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    xb_g = xb.to(device)
    print(f"GPU              : {torch.cuda.get_device_name(0)}")
    print(f"model device     : {next(model.parameters()).device}")
    print(f"batch device     : {xb_g.device}")
    print(f"model parameters : {n_params / 1e6:.2f} M")
    print(f"in_channels={model_cfg.in_channels}  classes={model_cfg.classes}")
    gpu_ok = (next(model.parameters()).device.type == "cuda" and xb_g.device.type == "cuda")
    print(f"GPU actually used: {gpu_ok}")
    del xb_g
    results["GPU"] = gpu_ok

    # ---------------- 4-5. TRAIN 2 REAL EPOCHS ---------------- #
    banner("4-5. REAL TRAINING (2 EPOCHS) - LOSS AND WEIGHT CHANGE")
    fp_before = parameter_fingerprint(model)
    print(f"parameter fingerprint BEFORE : {fp_before[:32]}...")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = NetraTrainingConfig(epochs=args.epochs, batch_size=args.batch_size,
                              lr=3e-4, weight_decay=1e-4, warmup_epochs=0,
                              patience=0, amp=True, seed=args.seed,
                              checkpoint_dir=str(CKPT_DIR))
    trainer = NetraTrainer(
        cfg, device="cuda", loss_name="dice_ce", class_weights=[1.0, 10.0],
        monitor="iou_oil", log_interval=5,
        provenance={
            "dataset_version": train_ds.dataset_version,
            "manifest_hash": man_hash,
            "normalization_version": train_ds.normalization["normalization_version"],
            "experiment_id": "netra_v02_smoke",
        },
    )
    res = trainer.train(model, train_loader, val_loader, "netra_v02_smoke",
                        epochs=args.epochs,
                        log_path=OUT / "06_smoke_train_log.jsonl")

    losses = [h["train_loss"] for h in res.history]
    print(f"\nEpoch 1 train loss : {losses[0]:.6f}")
    if len(losses) > 1:
        print(f"Epoch 2 train loss : {losses[1]:.6f}")
    print(f"Epoch 1 val   loss : {res.history[0]['val_loss']:.6f}")
    loss_ok = all(np.isfinite(l) for l in losses) and len(set(f"{l:.10f}" for l in losses)) > 1
    print(f"losses are finite and epoch-varying (not a constant) : {loss_ok}")
    results["FORWARD"] = all(np.isfinite(l) for l in losses)
    results["LOSS"] = loss_ok
    results["BACKWARD"] = res.weights_changed

    print(f"\nparameter fingerprint AFTER  : {res.fingerprint_after[:32]}...")
    print(f"WEIGHTS CHANGED : {res.weights_changed}")
    results["WEIGHTS_CHANGED"] = res.weights_changed
    evidence["training"] = {
        "epoch_losses": losses,
        "history": res.history,
        "fingerprint_before": res.fingerprint_before,
        "fingerprint_after": res.fingerprint_after,
        "weights_changed": res.weights_changed,
        "peak_vram_gb": res.peak_vram_gb,
        "seconds": res.total_seconds,
    }

    # ---------------- 6. METRICS ARE DYNAMIC ---------------- #
    banner("6. METRICS ARE DYNAMIC (NOT CONSTANTS)")
    ev = NetraEvaluator(amp=True)
    m_trained = ev.evaluate(model, val_loader, device=device, split="val")
    fresh = create_netra_model(NetraModelConfig(encoder_name="resnet34", encoder_weights=None,
                                                in_channels=2, classes=2)).to(device)
    m_fresh = ev.evaluate(fresh, val_loader, device=device, split="val")
    m_biased = ev.evaluate(BiasedHead(model, +20.0).to(device), val_loader,
                           device=device, split="val")

    def line(tag, m):
        o = m.overall
        print(f"  {tag:22s} IoU={o['iou_oil']:.6f} Dice={o['dice_oil']:.6f} "
              f"P={o['precision_oil']:.6f} R={o['recall_oil']:.6f} "
              f"F1={o['f1_oil']:.6f} PR-AUC={m.pr_auc:.6f}")

    line("trained model", m_trained)
    line("fresh random model", m_fresh)
    line("forced all-OIL", m_biased)

    keys = ("iou_oil", "dice_oil", "precision_oil", "recall_oil", "f1_oil")
    differs_fresh = any(abs(m_trained.overall[k] - m_fresh.overall[k]) > 1e-9 for k in keys)
    forced_recall = m_biased.overall["recall_oil"]
    dynamic_ok = differs_fresh and forced_recall > 0.99
    print(f"\n  trained vs fresh model metrics differ : {differs_fresh}")
    print(f"  forced-all-OIL recall == 1.0          : {forced_recall:.6f}")
    print(f"  METRICS DYNAMIC : {dynamic_ok}")
    known_stub = {0.75, 0.80, 0.82, 0.92}
    hits = {k: m_trained.overall[k] for k in keys if round(m_trained.overall[k], 2) in known_stub}
    print(f"  matches any hardcoded v0.1 stub constant : {bool(hits)} {hits if hits else ''}")
    results["METRICS_DYNAMIC"] = dynamic_ok
    evidence["metrics"] = {
        "trained": m_trained.to_dict(),
        "fresh_random": m_fresh.to_dict(),
        "forced_all_oil": m_biased.to_dict(),
    }
    del fresh

    # ---------------- 7. CHECKPOINT IS REAL ---------------- #
    banner("7. CHECKPOINT CONTENT")
    ck_path = Path(res.best_checkpoint)
    ck = torch.load(ck_path, map_location="cpu", weights_only=False)
    required = ["model_state_dict", "optimizer_state_dict", "scheduler_state_dict",
                "scaler_state_dict", "epoch", "best_metric", "config",
                "dataset_version", "manifest_hash", "normalization_version", "seed"]
    present = {k: (k in ck and ck[k] is not None) for k in required}
    for k, v in present.items():
        val = ck.get(k)
        shown = (f"{len(val)} tensors" if k == "model_state_dict"
                 else (str(val)[:60] if not isinstance(val, dict) else "<dict>"))
        print(f"  {k:24s} {'OK ' if v else 'MISSING'}  {shown}")
    ckpt_ok = all(present.values()) and ck_path.stat().st_size > 1_000_000
    print(f"  file size : {ck_path.stat().st_size / 1e6:.1f} MB")
    print(f"  CHECKPOINT REAL : {ckpt_ok}")
    results["CHECKPOINT"] = ckpt_ok
    evidence["checkpoint"] = {
        "path": str(ck_path), "size_mb": ck_path.stat().st_size / 1e6,
        "epoch": ck.get("epoch"), "best_metric": ck.get("best_metric"),
        "dataset_version": ck.get("dataset_version"),
        "manifest_hash": ck.get("manifest_hash"),
        "normalization_version": ck.get("normalization_version"),
        "keys_present": present,
    }

    # ---------------- 8. CHECKPOINT RELOAD ---------------- #
    banner("8. CHECKPOINT RELOAD AND INFERENCE")
    reloaded = create_netra_model(NetraModelConfig(encoder_name="resnet34", encoder_weights=None,
                                                   in_channels=2, classes=2))
    reloaded.load_state_dict(ck["model_state_dict"])
    reloaded.to(device).eval()
    fp_reloaded = parameter_fingerprint(reloaded)

    fixed_x, fixed_y, _ = next(iter(val_loader))
    with torch.no_grad():
        out = reloaded(fixed_x.to(device))
    print(f"  inference output shape : {tuple(out.shape)}")
    print(f"  expected               : ({fixed_x.shape[0]}, 2, 512, 512)")
    shape_ok = tuple(out.shape) == (fixed_x.shape[0], 2, 512, 512)
    print(f"  output finite          : {bool(torch.isfinite(out).all())}")
    reload_ok = shape_ok and bool(torch.isfinite(out).all())
    print(f"  CHECKPOINT RELOAD : {reload_ok}")
    results["RELOAD"] = reload_ok
    evidence["reload"] = {"output_shape": list(out.shape), "fingerprint": fp_reloaded}

    # ---------------- 9. GPU USAGE ---------------- #
    banner("9. GPU USAGE")
    peak = torch.cuda.max_memory_allocated() / 1024 ** 3
    reserved = torch.cuda.max_memory_reserved() / 1024 ** 3
    elapsed = time.perf_counter() - t_start
    tiles_seen = len(train_ds) * args.epochs
    print(f"  CUDA available   : {torch.cuda.is_available()}")
    print(f"  GPU              : {torch.cuda.get_device_name(0)}")
    print(f"  peak VRAM alloc  : {peak:.2f} GB")
    print(f"  peak VRAM resvd  : {reserved:.2f} GB")
    print(f"  training seconds : {res.total_seconds:.1f}")
    print(f"  throughput       : {tiles_seen / res.total_seconds:.2f} tiles/s (MEASURED)")
    print(f"  total wall clock : {elapsed:.1f} s")
    evidence["gpu"] = {"name": torch.cuda.get_device_name(0), "peak_vram_gb": peak,
                       "peak_reserved_gb": reserved, "train_seconds": res.total_seconds,
                       "tiles_per_s": tiles_seen / res.total_seconds}

    # ---------------- VERDICT ---------------- #
    order = ["DATA", "DATALOADER", "GPU", "FORWARD", "LOSS", "BACKWARD",
             "WEIGHTS_CHANGED", "METRICS_DYNAMIC", "CHECKPOINT", "RELOAD"]
    banner("REAL_SMOKE_TEST")
    for k in order:
        print(f"{k:18s} = {'PASS' if results.get(k) else 'FAIL'}")
    authorized = all(results.get(k) for k in order)
    print()
    print(f"LONG_TRAINING_AUTHORIZED = {str(authorized).upper()}")

    (OUT / "06_smoke_test.json").write_text(json.dumps({
        "results": {k: bool(results.get(k)) for k in order},
        "long_training_authorized": authorized,
        "scientific_status": "EXPERIMENTAL / UNVALIDATED",
        "evidence": evidence,
    }, indent=2, default=str))
    print(f"\nevidence -> {OUT / '06_smoke_test.json'}")
    return 0 if authorized else 7


if __name__ == "__main__":
    sys.exit(main())
