"""NETRA v0.3 DOMAIN-EXPANSION PILOT trainer.

Combines v0.2 STRONG_PIXEL Zenodo tiles (the only source of confirmed
positive pixels) with ESSD/PANGAEA WEAK_BOX tiles under a MIL existence
constraint, at a declared weak-sampling ratio.

This is a PILOT. It is not final production NETRA, not a segmentation
benchmark, and not evidence of accuracy improvement.

HARD REFUSALS (enforced at startup, not by convention):
  * Zenodo Part III        -- locked external evaluation
  * MC20                   -- external deployment case
  * CALM-GRD-HOLDOUT       -- primary independent evaluation
None of these may appear as a training input. The run aborts if they do.

Early stopping is DISABLED by design: the only uncontaminated evaluation
surface is the holdout, and the holdout must never influence training.
v0.3 val is source-proximity contaminated (3/3 scenes), so selecting on
it would select for the OLD domain. A fixed epoch budget is used and the
full trajectory is reported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
import yaml
from torch.utils.data import Dataset

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "packages"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from varuna_netra.dataset.gold_v03 import NetraGoldV03Dataset  # noqa: E402
from varuna_netra.model.config import NetraModelConfig  # noqa: E402
from varuna_netra.model.factory import create_netra_model  # noqa: E402
from varuna_netra.training.weak_supervision import (  # noqa: E402
    IGNORE_INDEX,
    NEGATIVE_OR_LOOKALIKE,
    STRONG_PIXEL,
    WEAK_BOX_OIL,
    NetraV03WeakSupervisionLoss,
)

FORBIDDEN_TRAINING_SUBSTRINGS = (
    "zenodo_part3", "netra_v03_sources/zenodo_part3",
    "mc20", "events/mc20",
    "/holdout/", "\\holdout\\",
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "UNKNOWN"


def assert_not_forbidden(paths: list[str]) -> None:
    for p in paths:
        low = str(p).lower().replace("\\", "/")
        for bad in FORBIDDEN_TRAINING_SUBSTRINGS:
            if bad.replace("\\", "/") in low:
                raise SystemExit(
                    f"REFUSING TO TRAIN: forbidden evaluation data in training inputs: {p} "
                    f"(matched {bad!r}). Part III, MC20 and the CALM-GRD-HOLDOUT are "
                    "evaluation-only."
                )


class StrongGoldDataset(Dataset):
    """v0.2 Gold tiles (already normalized at build time). READ-ONLY."""

    def __init__(self, manifest_path: Path, split: str = "train", limit: int | None = None):
        man = json.loads(Path(manifest_path).read_text())
        self.records = sorted(
            (t for t in man["tiles"] if t["split"] == split), key=lambda t: t["tile_id"]
        )
        if limit:
            self.records = self.records[:limit]
        assert_not_forbidden([r["img"] for r in self.records[:50]])

    def __len__(self):
        return len(self.records)

    def __getitem__(self, i):
        r = self.records[i]
        img = np.load(REPO / r["img"]).astype(np.float32)
        mask = np.load(REPO / r["mask"]).astype(np.int64)
        return (
            torch.from_numpy(img),
            torch.from_numpy(mask),
            torch.zeros(mask.shape, dtype=torch.bool),   # no boxes in strong data
            STRONG_PIXEL,
        )


class WeakEssdDataset(Dataset):
    """v0.3 ESSD tiles: raw dB, normalized here with v0.2's frozen transform."""

    def __init__(self, records_path: Path, split: str, normalization: dict):
        if split != "train":
            raise SystemExit(f"WeakEssdDataset refuses split={split!r}; training uses 'train' only")
        self.ds = NetraGoldV03Dataset(
            records_path, split=split, repo_root=REPO,
            normalization=normalization, apply_ignore=True, return_meta=True,
        )
        self.gold = REPO / "data" / "gold" / "netra_v0_3"

    def __len__(self):
        return len(self.ds)

    def __getitem__(self, i):
        img, target, meta = self.ds[i]
        rec = self.ds.records[i]
        ignore = np.load(self.gold / rec["split"] / f"{rec['tile_id']}_ignore.npy").astype(bool)
        stype = WEAK_BOX_OIL if meta["semantic_class"] == "OIL" else NEGATIVE_OR_LOOKALIKE
        return img, target, torch.from_numpy(ignore), stype


def interleaved_indices(n_strong: int, n_weak: int, weak_ratio: float, steps: int,
                        batch_size: int, seed: int):
    """Deterministic scene-aware interleaving: a fixed fraction of every
    sampling window is weak. No file duplication -- indices only."""
    rng = np.random.default_rng(seed)
    per_batch_weak = weak_ratio * batch_size
    batches = []
    carry = 0.0
    for _ in range(steps):
        carry += per_batch_weak
        k = int(carry)
        carry -= k
        k = min(k, batch_size)
        w = rng.integers(0, n_weak, size=k).tolist() if k else []
        s = rng.integers(0, n_strong, size=batch_size - k).tolist()
        batches.append((s, w))
    return batches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-steps", type=int, default=None, help="smoke/debug cap")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    seed = int(cfg["seed"])
    torch.manual_seed(seed)
    np.random.seed(seed)

    strong_manifest = REPO / cfg["strong_source"]["records"]
    weak_records = REPO / cfg["weak_source"]["records"]
    norm = json.loads((REPO / cfg["normalization"]["file"]).read_text())
    assert_not_forbidden([str(strong_manifest), str(weak_records)])

    strong = StrongGoldDataset(strong_manifest, "train", limit=cfg.get("strong_limit"))
    weak = WeakEssdDataset(weak_records, "train", norm)
    print(f"strong train tiles = {len(strong)} | weak train tiles = {len(weak)}")

    model = create_netra_model(NetraModelConfig(
        encoder_name=cfg["architecture"]["encoder_name"],
        encoder_weights=cfg["architecture"]["encoder_weights"],
        in_channels=cfg["architecture"]["in_channels"],
        classes=cfg["architecture"]["classes"],
    )).to(args.device)

    crit = NetraV03WeakSupervisionLoss(
        w_strong=cfg["loss"]["w_strong"],
        w_weak_negative=cfg["loss"]["w_weak_negative"],
        w_mil=cfg["loss"]["w_mil"],
        topk_frac=cfg["loss"]["mil_topk_frac"],
        topk_min=cfg["loss"]["mil_topk_min"],
    )
    opt = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]))

    grad_clip = float(cfg.get("grad_clip_norm", 5.0))
    # Coprime with the weak-sampler period (1/weak_ratio) so logged steps
    # cannot alias onto a single phase. See the window means below.
    log_every = int(cfg.get("log_every_steps", 17))

    def fresh_acc():
        return {"n": 0, "total": 0.0, "strong": 0.0, "weak_neg": 0.0, "mil": 0.0,
                "n_weak": 0, "n_boxes": 0, "mil_when_box": 0.0, "n_mil_steps": 0}
    acc = fresh_acc()
    bs = int(cfg["batch_size"])
    ratio = float(cfg["weak_sampling_ratio"])
    steps_per_epoch = cfg.get("steps_per_epoch") or (len(strong) // max(1, int(bs * (1 - ratio))))
    epochs = int(cfg["epoch_budget"])
    if args.max_steps:
        steps_per_epoch = min(steps_per_epoch, args.max_steps)
        epochs = 1

    run_meta = {
        "experiment_id": cfg["experiment_id"],
        "git_commit": git_commit(),
        "dataset_version": cfg["dataset_version"],
        "strong_manifest_sha256": sha256_file(strong_manifest),
        "weak_records_sha256": sha256_file(weak_records),
        "normalization_version": cfg["normalization"]["version"],
        "normalization_sha256": sha256_file(REPO / cfg["normalization"]["file"]),
        "seed": seed, "optimizer": "adamw", "learning_rate": cfg["learning_rate"],
        "batch_size": bs, "weak_sampling_ratio": ratio, "grad_clip_norm": grad_clip,
        "log_every_steps": log_every,
        "epoch_budget": epochs, "steps_per_epoch": steps_per_epoch,
        "loss": cfg["loss"], "early_stopping": "DISABLED (fixed epoch budget)",
        "python": platform.python_version(), "torch": torch.__version__,
        "cuda": torch.version.cuda, "device": args.device,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
    }
    (out / "run_metadata.json").write_text(json.dumps(run_meta, indent=2))
    print(json.dumps(run_meta, indent=2))

    log_path = out / "metrics.jsonl"
    t0 = time.time()
    for epoch in range(epochs):
        batches = interleaved_indices(len(strong), len(weak), ratio, steps_per_epoch, bs, seed + epoch)
        model.train()
        for step, (si, wi) in enumerate(batches):
            xs, ts, bs_, tys = [], [], [], []
            for i in si:
                a, b, c, t = strong[i]; xs.append(a); ts.append(b); bs_.append(c); tys.append(t)
            for i in wi:
                a, b, c, t = weak[i]; xs.append(a); ts.append(b); bs_.append(c); tys.append(t)
            x = torch.stack(xs).to(args.device)
            y = torch.stack(ts).to(args.device)
            bm = torch.stack(bs_).to(args.device)

            opt.zero_grad()
            o = crit(model(x), y, tys, bm)
            # accumulate over EVERY step, not just logged ones -- the weak
            # sampler has period 1/weak_ratio, so sampling a single step at a
            # fixed interval can alias onto one phase and hide MIL entirely.
            acc["n"] += 1
            acc["total"] += float(o.total); acc["strong"] += float(o.strong)
            acc["weak_neg"] += float(o.weak_negative); acc["mil"] += float(o.mil)
            acc["n_weak"] += o.n_weak; acc["n_boxes"] += o.n_boxes
            if o.n_boxes:
                acc["mil_when_box"] += float(o.mil); acc["n_mil_steps"] += 1
            if not torch.isfinite(o.total):
                print(f"[NAN-GUARD] epoch {epoch} step {step}: non-finite loss, batch skipped")
                with open(log_path, "a") as fh:
                    fh.write(json.dumps({"epoch": epoch, "step": step, "nan_guard": True}) + "\n")
                continue
            o.total.backward()
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            opt.step()

            if step % log_every == 0:
                n = max(acc["n"], 1)
                rec = {
                    "epoch": epoch, "step": step, "elapsed_s": round(time.time() - t0, 1),
                    # instantaneous (this step only)
                    "loss_total": float(o.total), "loss_strong": float(o.strong),
                    "loss_weak_negative": float(o.weak_negative), "loss_mil": float(o.mil),
                    "grad_norm": float(gn), "n_strong": o.n_strong, "n_weak": o.n_weak,
                    "n_boxes": o.n_boxes,
                    # window means over EVERY step since the last log -- these are
                    # the alias-proof numbers to read the trajectory from
                    "win_steps": acc["n"],
                    "win_loss_total": acc["total"] / n, "win_loss_strong": acc["strong"] / n,
                    "win_loss_weak_negative": acc["weak_neg"] / n, "win_loss_mil": acc["mil"] / n,
                    "win_mil_when_box": (acc["mil_when_box"] / acc["n_mil_steps"]) if acc["n_mil_steps"] else None,
                    "win_steps_with_box": acc["n_mil_steps"], "win_weak_samples": acc["n_weak"],
                    "win_boxes": acc["n_boxes"],
                }
                acc = fresh_acc()
                if torch.cuda.is_available():
                    rec["vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
                print(rec)
                with open(log_path, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")

        ck = {"model": model.state_dict(), "optimizer": opt.state_dict(),
              "epoch": epoch, "run_metadata": run_meta}
        torch.save(ck, out / "last.pt")          # never writes into artifacts/checkpoints/netra_v0_2
    print(f"done in {time.time()-t0:.1f}s -- evaluate on the CALM-GRD-HOLDOUT separately, never here")


if __name__ == "__main__":
    main()
