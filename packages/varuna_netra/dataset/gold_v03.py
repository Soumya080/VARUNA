"""NETRA-GOLD-v0.3 loader (weak-label aware).

Separate from `gold.py` by design: the v0.2 loader is used by the frozen
v0.2 baseline and must not change. This module adds what v0.3 needs and
v0.2 does not have:

  * `label_quality` per sample (WEAK_BOX / STRONG_PIXEL / COARSE_REGION /
    UNKNOWN) -- v0.3's PANGAEA-derived labels are WEAK_BOX and must never
    be silently consumed as if they were pixel-precise masks.
  * an `ignore` mask, so a loss can exclude pixels whose identity is
    genuinely unknown (the interior of a bounding box, where a measured
    ~62% of pixels are NOT plausibly oil -- see
    data/gold/netra_v0_3/reports/phase6_box_label_noise.json).
  * full per-tile metadata passthrough.

Membership is manifest-driven, deterministic, and never glob-discovered,
same principle as the v0.2 loader.

Channel order is the v0.3 polarization contract: channel 0 = VH,
channel 1 = VV (see docs/datasets/NETRA_V03_POLARIZATION_CONTRACT.md).
This matches what the frozen v0.2 checkpoint actually learned, so a
v0.2-vs-v0.3 comparison is not confounded by a channel-order change.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset

EXPECTED_CHANNELS = 2
VALID_SPLITS = ("train", "val", "holdout")
VALID_LABEL_QUALITY = ("STRONG_PIXEL", "WEAK_BOX", "COARSE_REGION", "UNKNOWN")

# Sentinel value for pixels excluded from the loss. Chosen to not collide
# with the 0/1 class ids.
IGNORE_INDEX = 255


class GoldV03Error(RuntimeError):
    """Raised when the v0.3 records are absent, malformed, or inconsistent with disk."""


class NetraGoldV03Dataset(Dataset):
    """Manifest-driven NETRA-GOLD-v0.3 tiles with weak-label semantics.

    Yields (image, target) or (image, target, meta):
        image:  float32 [2, H, W]   channel 0 = VH, channel 1 = VV (Sigma0 dB)
        target: int64   [H, W]      0 = NOT_OIL, 1 = OIL(weak), 255 = IGNORE

    When `apply_ignore` is True (the default), pixels inside an annotation
    box are set to IGNORE_INDEX rather than 1, because the source evidence
    does not identify WHICH pixels in the box are oil. Set apply_ignore
    False only to deliberately reproduce the naive weak-box-as-positive
    formulation, and say so in the experiment record.
    """

    def __init__(
        self,
        records_path: str | Path,
        split: str,
        repo_root: str | Path | None = None,
        apply_ignore: bool = True,
        return_meta: bool = False,
        normalization: dict[str, Any] | None = None,
    ) -> None:
        if split not in VALID_SPLITS:
            raise ValueError(f"split must be one of {VALID_SPLITS}, got {split!r}")

        self.records_path = Path(records_path)
        if not self.records_path.exists():
            raise GoldV03Error(
                f"v0.3 tile records not found: {self.records_path}. "
                "Refusing to glob-discover tiles from disk."
            )
        self.repo_root = Path(repo_root) if repo_root else self.records_path.resolve().parents[3]
        self.split = split
        self.apply_ignore = apply_ignore
        self.return_meta = return_meta
        self.normalization = normalization

        with open(self.records_path) as fh:
            all_records = json.load(fh)

        # Deterministic ordering; excluded duplicates are never yielded.
        self.records = sorted(
            (r for r in all_records if r.get("final_split") == split),
            key=lambda r: r["tile_id"],
        )
        if not self.records:
            raise GoldV03Error(f"no records for split {split!r} in {self.records_path}")

        for r in self.records:
            lq = r.get("label_quality", "UNKNOWN")
            if lq not in VALID_LABEL_QUALITY:
                raise GoldV03Error(f"tile {r['tile_id']}: invalid label_quality {lq!r}")

    def __len__(self) -> int:
        return len(self.records)

    def _tile_dir(self, rec: dict) -> Path:
        # `split` here is the on-disk directory the tile was written into
        # (train/holdout), which is not necessarily the final logical split.
        return self.repo_root / "data" / "gold" / "netra_v0_3" / rec["split"]

    def label_quality_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r["label_quality"]] = counts.get(r["label_quality"], 0) + 1
        return counts

    def __getitem__(self, idx: int):
        rec = self.records[idx]
        d = self._tile_dir(rec)
        img_path = d / f"{rec['tile_id']}_img.npy"
        mask_path = d / f"{rec['tile_id']}_mask.npy"
        ignore_path = d / f"{rec['tile_id']}_ignore.npy"

        if not img_path.exists():
            raise GoldV03Error(f"manifested tile missing on disk: {img_path}")

        img = np.load(img_path).astype(np.float32)
        if img.shape[0] != EXPECTED_CHANNELS:
            raise GoldV03Error(f"{rec['tile_id']}: expected {EXPECTED_CHANNELS} channels, got {img.shape[0]}")

        mask = np.load(mask_path).astype(np.int64)

        # nodata (NaN) -> a finite sentinel, matching v0.2's convention of
        # collapsing nodata to the low clip bound rather than leaving NaN.
        if self.normalization:
            lo = self.normalization["clip_low"]
            hi = self.normalization["clip_high"]
            for ci, pol in enumerate(("VH", "VV")):
                ch = img[ci]
                ch = np.clip(ch, lo[pol], hi[pol])
                ch = (ch - lo[pol]) / max(hi[pol] - lo[pol], 1e-6)
                img[ci] = np.nan_to_num(ch, nan=0.0)
        else:
            img = np.nan_to_num(img, nan=0.0)

        target = mask
        if self.apply_ignore and ignore_path.exists():
            ignore = np.load(ignore_path).astype(bool)
            target = np.where(ignore, IGNORE_INDEX, mask).astype(np.int64)

        image_t = torch.from_numpy(img)
        target_t = torch.from_numpy(target)

        if not self.return_meta:
            return image_t, target_t
        meta = {
            "sample_id": rec["sample_id"],
            "scene_id": rec["scene_id"],
            "product_id": rec["product_id"],
            "label_quality": rec["label_quality"],
            "label_type": rec["label_type"],
            "semantic_class": rec["semantic_class"],
            "wind_regime": rec["wind_regime"],
            "wind_speed_ms": rec.get("wind_speed_ms"),
            "acquisition_timestamp": rec["acquisition_timestamp"],
            "final_split": rec["final_split"],
        }
        return image_t, target_t, meta
