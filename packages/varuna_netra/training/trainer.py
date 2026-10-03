"""
NETRA trainer (Phase 19).

Replaces the M5 stub whose epoch loop body was `pass` and which saved a
randomly-initialised state_dict as a "best checkpoint". This implementation
performs real forward/loss/backward/optimizer work and every logged number is
measured from the data it was computed on.

Hard safety properties:
  * requesting CUDA when CUDA is unavailable raises, it never falls back silently
  * no synthetic data path exists in this module
  * checkpoints carry dataset version, manifest hash and normalization version
    so a run can always be traced back to the exact Gold it consumed
"""
from __future__ import annotations

import gc
import json

import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from .config import NetraTrainingConfig
from .evaluator import NetraEvaluator
from .losses import build_loss


class CudaUnavailableError(RuntimeError):
    """Raised when cuda was requested but is not available. Never downgrade silently."""


def resolve_device(requested: str) -> torch.device:
    req = (requested or "cpu").lower()
    if req in ("cuda", "gpu"):
        if not torch.cuda.is_available():
            raise CudaUnavailableError(
                "device='cuda' was requested but torch.cuda.is_available() is False. "
                "Refusing to silently train on CPU. Check that the project interpreter "
                "(.venv/Scripts/python.exe) is in use and that a CUDA build of torch is "
                "installed; the system python on this machine carries a CPU-only build."
            )
        return torch.device("cuda")
    if req == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(req)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


def parameter_fingerprint(model: nn.Module) -> str:
    """Order-stable fingerprint of all parameters, used to prove weights changed."""
    import hashlib

    h = hashlib.sha256()
    for name, p in sorted(model.state_dict().items()):
        h.update(name.encode())
        t = p.detach().to("cpu")
        if t.is_floating_point():
            t = t.float()
        h.update(np.ascontiguousarray(t.numpy()).tobytes())
    return h.hexdigest()


@dataclass
class EpochRecord:
    epoch: int
    train_loss: float
    val_loss: float
    val_iou_oil: float
    val_dice_oil: float
    val_precision_oil: float
    val_recall_oil: float
    val_f1_oil: float
    val_pr_auc: float
    lr: float
    seconds: float
    peak_vram_gb: float
    samples_per_s: float

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class TrainResult:
    experiment_id: str
    best_checkpoint: str
    last_checkpoint: str
    best_metric: float
    best_epoch: int
    epochs_run: int
    history: list[dict[str, Any]] = field(default_factory=list)
    fingerprint_before: str = ""
    fingerprint_after: str = ""
    weights_changed: bool = False
    device: str = ""
    peak_vram_gb: float = 0.0
    total_seconds: float = 0.0


class NetraTrainer:
    """Real supervised training loop for the NETRA segmentation model."""

    def __init__(
        self,
        config: NetraTrainingConfig,
        device: str = "cuda",
        loss_name: str = "dice_ce",
        class_weights: list[float] | None = None,
        monitor: str = "iou_oil",
        provenance: dict[str, Any] | None = None,
        log_interval: int = 20,
    ) -> None:
        self.config = config
        self.device = resolve_device(device)
        self.loss_name = loss_name
        self.class_weights = class_weights
        self.monitor = monitor
        self.provenance = provenance or {}
        self.log_interval = int(log_interval)
        self.evaluator = NetraEvaluator(amp=config.amp)

    # ------------------------------------------------------------------ #
    def _build_optimizer(self, model: nn.Module):
        return torch.optim.AdamW(
            model.parameters(), lr=self.config.lr, weight_decay=self.config.weight_decay
        )

    def _build_scheduler(self, optimizer, total_epochs: int):
        warmup = max(0, int(self.config.warmup_epochs))
        warmup = min(warmup, max(0, total_epochs - 1))

        def lr_lambda(epoch: int) -> float:
            if warmup and epoch < warmup:
                return float(epoch + 1) / float(warmup)
            if total_epochs <= warmup:
                return 1.0
            progress = (epoch - warmup) / max(1, total_epochs - warmup)
            return 0.5 * (1.0 + float(np.cos(np.pi * min(1.0, progress))))

        return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    def _save(
        self, path: Path, model, optimizer, scheduler, scaler,
        epoch: int, best_metric: float, history: list[dict[str, Any]],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict() if scheduler else None,
            "scaler_state_dict": scaler.state_dict() if scaler is not None else None,
            "epoch": epoch,
            "best_metric": best_metric,
            "monitor": self.monitor,
            "config": self.config.model_dump(),
            "loss": self.loss_name,
            "class_weights": self.class_weights,
            "seed": self.config.seed,
            "history": history,
            "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
        payload.update(
            {
                "dataset_version": self.provenance.get("dataset_version"),
                "manifest_hash": self.provenance.get("manifest_hash"),
                "normalization_version": self.provenance.get("normalization_version"),
                "git_commit": self.provenance.get("git_commit"),
                "config_hash": self.provenance.get("config_hash"),
                "experiment_id": self.provenance.get("experiment_id"),
            }
        )
        torch.save(payload, path)

    # ------------------------------------------------------------------ #
    def train(
        self,
        model: nn.Module,
        train_loader: Any,
        val_loader: Any,
        experiment_id: str,
        epochs: int | None = None,
        resume_from: str | Path | None = None,
        log_path: str | Path | None = None,
    ) -> TrainResult:
        seed_everything(self.config.seed)
        total_epochs = int(epochs if epochs is not None else self.config.epochs)
        ckpt_dir = Path(self.config.checkpoint_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        best_path = ckpt_dir / f"{experiment_id}_best.pt"
        last_path = ckpt_dir / f"{experiment_id}_last.pt"

        model = model.to(self.device)
        fp_before = parameter_fingerprint(model)

        loss_fn = build_loss(self.loss_name, class_weights=self.class_weights).to(self.device)
        optimizer = self._build_optimizer(model)
        scheduler = self._build_scheduler(optimizer, total_epochs)
        use_amp = bool(self.config.amp) and self.device.type == "cuda"
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

        start_epoch, best_metric, history, bad_epochs = 0, -float("inf"), [], 0
        if resume_from:
            rp = Path(resume_from)
            if rp.exists():
                ck = torch.load(rp, map_location=self.device, weights_only=False)
                model.load_state_dict(ck["model_state_dict"])
                optimizer.load_state_dict(ck["optimizer_state_dict"])
                if ck.get("scheduler_state_dict"):
                    scheduler.load_state_dict(ck["scheduler_state_dict"])
                if ck.get("scaler_state_dict") and scaler is not None:
                    scaler.load_state_dict(ck["scaler_state_dict"])
                start_epoch = int(ck["epoch"])
                best_metric = float(ck.get("best_metric", -float("inf")))
                history = list(ck.get("history", []))
                print(f"[RESUME] from {rp} at epoch {start_epoch}, best={best_metric:.4f}")
            else:
                raise FileNotFoundError(f"resume_from does not exist: {rp}")

        if self.device.type == "cuda":
            torch.cuda.reset_peak_memory_stats()

        log_fh = open(log_path, "a", encoding="utf-8") if log_path else None
        best_epoch = start_epoch
        t_start = time.perf_counter()

        try:
            for epoch in range(start_epoch, total_epochs):
                model.train()
                t0 = time.perf_counter()
                running, n_batches, n_seen = 0.0, 0, 0

                for step, batch in enumerate(train_loader):
                    images, masks = batch[0], batch[1]
                    images = images.to(self.device, non_blocking=True)
                    masks = masks.to(self.device, non_blocking=True)

                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast("cuda", enabled=use_amp):
                        logits = model(images)
                        loss = loss_fn(logits, masks)

                    if not torch.isfinite(loss):
                        raise RuntimeError(
                            f"non-finite loss at epoch {epoch + 1} step {step}: {loss.item()}"
                        )

                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                    scaler.step(optimizer)
                    scaler.update()

                    running += float(loss.item())
                    n_batches += 1
                    n_seen += images.shape[0]
                    if self.log_interval and step % self.log_interval == 0:
                        msg = (f"  ep{epoch + 1:>3} step{step:>5} "
                               f"loss={loss.item():.4f} lr={optimizer.param_groups[0]['lr']:.2e}")
                        print(msg, flush=True)
                        if log_fh:
                            log_fh.write(msg + "\n"); log_fh.flush()

                train_loss = running / max(1, n_batches)
                epoch_s = time.perf_counter() - t0

                # 2026-08-29: mitigation for a slow per-epoch memory accumulation
                # (persistent DataLoader workers + pinned buffers) that exhausted
                # the Windows paging file at epoch 15 of a real run. Explicit
                # collection at the train/val boundary is cheap relative to a
                # multi-minute epoch and does not change persistent_workers=True
                # (which is required for stability -- see build_loaders in
                # train_netra.py for why the non-persistent alternative was
                # reverted).
                gc.collect()
                if self.device.type == "cuda":
                    torch.cuda.empty_cache()

                metrics = self.evaluator.evaluate(
                    model, val_loader, device=self.device, loss_fn=loss_fn, split="val"
                )
                scheduler.step()

                peak_vram = (torch.cuda.max_memory_allocated() / 1024 ** 3
                             if self.device.type == "cuda" else 0.0)
                rec = EpochRecord(
                    epoch=epoch + 1,
                    train_loss=train_loss,
                    val_loss=metrics.loss,
                    val_iou_oil=metrics.overall["iou_oil"],
                    val_dice_oil=metrics.overall["dice_oil"],
                    val_precision_oil=metrics.overall["precision_oil"],
                    val_recall_oil=metrics.overall["recall_oil"],
                    val_f1_oil=metrics.overall["f1_oil"],
                    val_pr_auc=metrics.pr_auc,
                    lr=optimizer.param_groups[0]["lr"],
                    seconds=epoch_s,
                    peak_vram_gb=peak_vram,
                    samples_per_s=n_seen / epoch_s if epoch_s > 0 else 0.0,
                )
                history.append(rec.as_dict())
                line = (f"[EPOCH {epoch + 1}/{total_epochs}] "
                        f"train_loss={train_loss:.4f} val_loss={metrics.loss:.4f} "
                        f"IoU={rec.val_iou_oil:.4f} Dice={rec.val_dice_oil:.4f} "
                        f"P={rec.val_precision_oil:.4f} R={rec.val_recall_oil:.4f} "
                        f"F1={rec.val_f1_oil:.4f} PR-AUC={rec.val_pr_auc:.4f} "
                        f"lr={rec.lr:.2e} {epoch_s:.1f}s peakVRAM={peak_vram:.2f}GB")
                print(line, flush=True)
                if log_fh:
                    log_fh.write(json.dumps(rec.as_dict()) + "\n"); log_fh.flush()

                current = metrics.overall.get(self.monitor, float("nan"))
                if not np.isnan(current) and current > best_metric:
                    best_metric, best_epoch, bad_epochs = float(current), epoch + 1, 0
                    self._save(best_path, model, optimizer, scheduler, scaler,
                               epoch + 1, best_metric, history)
                    print(f"  -> new best {self.monitor}={best_metric:.4f}, saved {best_path.name}",
                          flush=True)
                else:
                    bad_epochs += 1

                self._save(last_path, model, optimizer, scheduler, scaler,
                           epoch + 1, best_metric, history)

                if self.config.patience and bad_epochs >= self.config.patience:
                    print(f"[EARLY STOP] no {self.monitor} improvement for "
                          f"{bad_epochs} epochs", flush=True)
                    break
        finally:
            if log_fh:
                log_fh.close()

        fp_after = parameter_fingerprint(model)
        if not best_path.exists():
            self._save(best_path, model, optimizer, scheduler, scaler,
                       best_epoch, best_metric, history)

        return TrainResult(
            experiment_id=experiment_id,
            best_checkpoint=str(best_path),
            last_checkpoint=str(last_path),
            best_metric=best_metric,
            best_epoch=best_epoch,
            epochs_run=len(history),
            history=history,
            fingerprint_before=fp_before,
            fingerprint_after=fp_after,
            weights_changed=(fp_before != fp_after),
            device=str(self.device),
            peak_vram_gb=(torch.cuda.max_memory_allocated() / 1024 ** 3
                          if self.device.type == "cuda" else 0.0),
            total_seconds=time.perf_counter() - t_start,
        )
