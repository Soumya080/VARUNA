"""
Build the NETRA v0.2 energy-score OOD reference distribution (Phase 4B).

READ-ONLY against frozen assets: loads NETRA-GOLD-v0.2 val tiles (via the
manifest-driven `NetraGoldDataset`, never a directory glob) and the frozen
v0.2 checkpoint, runs forward inference only (no gradient, no training step,
no weight update), and writes a single small reference-percentile file.

Does not modify data/gold/, data/manifests/, or any checkpoint file.

Energy score (Liu et al., 2020, "Energy-based Out-of-distribution Detection"):
    E(x) = -logsumexp(logits(x))
Lower energy => the model is more confident this input resembles what it was
trained on, for ANY class. It is a property of the pre-softmax logits, not of
the winning class's probability, which is why it is a genuinely different
signal from `max_probability` (the current heuristic) rather than a
relabelling of the same number.

Per tile, we take the MINIMUM per-pixel energy across the tile (the single
most in-domain-confident pixel), matching the existing convention of using a
tile's most extreme activation as its representative statistic. The reference
distribution is the set of these per-tile minima across a deterministic
sample of the val split.

This is NOT a calibrated OOD detector: no labeled OOD corpus was used to tune
a decision boundary, and no false-positive/false-negative rate has been
measured against a held-out set of true out-of-domain scenes. It is a
principled, reproducible, no-training summary of "how in-domain-confident
does NETRA v0.2 get on data resembling what it was trained on" - useful as a
reference to compare a new scene against, not as a trained classifier.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from varuna_netra.dataset.gold import NetraGoldDataset  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json"
CHECKPOINT = (REPO_ROOT / "artifacts" / "checkpoints" / "netra_v0_2" /
              "netra_baseline_v02_dac482fcd84a_best.pt")
OUT_PATH = REPO_ROOT / "reports" / "netra_v02" / "ood_energy_reference_v0_1.json"

SAMPLE_N = 200
SEED = 42


def logsumexp_np(logits: np.ndarray, axis: int) -> np.ndarray:
    m = np.max(logits, axis=axis, keepdims=True)
    return (m + np.log(np.sum(np.exp(logits - m), axis=axis, keepdims=True))).squeeze(axis)


def main() -> None:
    import segmentation_models_pytorch as smp

    ds = NetraGoldDataset(MANIFEST, split="val", limit=SAMPLE_N, limit_seed=SEED)
    print(f"Sampled {len(ds)} val tiles (seed={SEED}) from {MANIFEST.name}")

    model = smp.Unet(encoder_name="resnet34", encoder_weights=None,
                      in_channels=2, classes=2)
    blob = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    state = blob.get("model_state_dict", blob) if isinstance(blob, dict) else blob
    model.load_state_dict(state)
    model.eval()

    per_tile_min_energy: list[float] = []
    per_tile_max_prob: list[float] = []
    with torch.no_grad():
        for i in range(len(ds)):
            img, _mask = ds[i]
            x = img.unsqueeze(0)
            logits = model(x)[0].numpy()  # [C, H, W]
            energy_map = -logsumexp_np(logits, axis=0)  # [H, W], lower = more in-domain-confident
            per_tile_min_energy.append(float(energy_map.min()))
            probs = torch.softmax(torch.from_numpy(logits), dim=0)[1].numpy()
            per_tile_max_prob.append(float(probs.max()))
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(ds)} tiles scored")

    arr = np.array(per_tile_min_energy)
    percentiles = {str(p): float(np.percentile(arr, p))
                   for p in (1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99)}

    result = {
        "reference_version": "netra-v0.2-energy-ref-v0.1",
        "method": "energy_score = -logsumexp(logits); per-tile statistic = min over pixels",
        "computed_from": {
            "manifest": str(MANIFEST.relative_to(REPO_ROOT)),
            "manifest_sha256": ds.manifest_hash,
            "split": "val",
            "sample_n": len(ds),
            "sample_seed": SEED,
            "checkpoint_sha256": "9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66",
        },
        "no_training_performed": True,
        "calibrated": False,
        "limitations": [
            "No labeled out-of-domain corpus was used; this is a reference "
            "distribution over in-domain data, not a tuned decision boundary.",
            "No false-positive/false-negative rate has been measured against "
            "held-out true-OOD scenes.",
            "Sampled from 200 of 3616 val tiles for tractability; not the full split.",
            "Energy score is architecture- and checkpoint-specific; invalid for "
            "any other model version.",
        ],
        "percentiles": percentiles,
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "reference_max_prob_percentiles": {
            str(p): float(np.percentile(per_tile_max_prob, p))
            for p in (1, 5, 50, 95, 99)
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUT_PATH}")
    print(json.dumps(percentiles, indent=2))


if __name__ == "__main__":
    main()
