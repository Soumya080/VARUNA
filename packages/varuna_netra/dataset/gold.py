"""
NETRA real Gold dataset (Phase 16).

Membership is defined *exclusively* by a versioned manifest. A bare directory
glob is never authoritative: unmanifested files on disk are invisible to this
loader by construction, which is what keeps stale or differently-normalized
tiles out of a training batch.

There is deliberately no synthetic fallback anywhere in this module. If the
manifest or a referenced tile is missing, loading fails loudly.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import Dataset

EXPECTED_CHANNELS = 2          # 0=VV, 1=VH
EXPECTED_CLASSES = 2           # 0=NOT_OIL, 1=OIL
VALID_SPLITS = ("train", "val", "test")


class GoldManifestError(RuntimeError):
    """Raised when the manifest is absent, malformed, or inconsistent with disk."""


def manifest_sha256(manifest_path: str | Path) -> str:
    """Stable content hash of the manifest file, recorded in every checkpoint."""
    h = hashlib.sha256()
    with open(manifest_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class NetraGoldDataset(Dataset):
    """Manifest-driven NETRA Gold tiles.

    Yields:
        image: float32 tensor [2, H, W]  (VV, VH - normalized at Gold build time)
        mask:  int64   tensor [H, W]     (0 = NOT_OIL, 1 = OIL)
    """

    def __init__(
        self,
        manifest_path: str | Path,
        split: str,
        repo_root: str | Path | None = None,
        cache_in_ram: bool = False,
        limit: int | None = None,
        limit_seed: int = 42,
        return_meta: bool = False,
    ) -> None:
        if split not in VALID_SPLITS:
            raise ValueError(f"split must be one of {VALID_SPLITS}, got {split!r}")

        self.manifest_path = Path(manifest_path)
        if not self.manifest_path.exists():
            raise GoldManifestError(
                f"Gold manifest not found: {self.manifest_path}. "
                "Real training requires a real Gold manifest; refusing to substitute "
                "synthetic or directory-globbed data."
            )
        self.repo_root = Path(repo_root) if repo_root else self.manifest_path.resolve().parents[2]
        self.split = split
        self.return_meta = return_meta

        with open(self.manifest_path, encoding="utf-8") as fh:
            man = json.load(fh)
        self.manifest = man
        self.manifest_hash = manifest_sha256(self.manifest_path)

        self.dataset_id: str = man["dataset_id"]
        self.dataset_version: str = man["dataset_version"]
        self.normalization: dict[str, Any] = man["normalization"]
        self.label_mapping: dict[str, Any] = man["label_mapping"]
        self.tile_size: int = int(man["tiling"]["tile_size"])

        n_classes = len(self.label_mapping["classes"])
        if n_classes != EXPECTED_CLASSES:
            raise GoldManifestError(
                f"manifest declares {n_classes} classes; NETRA baseline expects {EXPECTED_CLASSES}"
            )
        n_ch = len(man["channels"])
        if n_ch != EXPECTED_CHANNELS:
            raise GoldManifestError(
                f"manifest declares {n_ch} channels; NETRA baseline expects {EXPECTED_CHANNELS}"
            )

        tiles = [t for t in man["tiles"] if t["split"] == split]
        if not tiles:
            raise GoldManifestError(f"manifest contains no tiles for split={split!r}")

        if limit is not None and limit < len(tiles):
            # Deterministic subsample for the smoke gate, drawn across the whole
            # split so the subset is not one scene's tiles.
            rng = np.random.default_rng(limit_seed)
            order = rng.permutation(len(tiles))
            tiles = [tiles[i] for i in sorted(order[:limit])]

        self.tiles = tiles
        self.scene_ids = sorted({t["scene_id"] for t in tiles})
        self.tile_ids = [t["tile_id"] for t in tiles]

        self._cache: dict[int, tuple[np.ndarray, np.ndarray]] | None = {} if cache_in_ram else None

        missing = [t["tile_id"] for t in tiles[:64] if not (self.repo_root / t["img"]).exists()]
        if missing:
            raise GoldManifestError(
                f"manifest references tiles that are not on disk, e.g. {missing[:3]}"
            )

    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self.tiles)

    def _load_raw(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        t = self.tiles[idx]
        img_p = self.repo_root / t["img"]
        msk_p = self.repo_root / t["mask"]
        try:
            img = np.load(img_p)
            msk = np.load(msk_p)
        except FileNotFoundError as exc:
            raise GoldManifestError(
                f"manifested tile {t['tile_id']} missing on disk ({exc.filename}); "
                "refusing to substitute data"
            ) from exc

        if img.shape != (EXPECTED_CHANNELS, self.tile_size, self.tile_size):
            raise GoldManifestError(
                f"tile {t['tile_id']} image shape {img.shape} != "
                f"({EXPECTED_CHANNELS},{self.tile_size},{self.tile_size})"
            )
        if msk.shape != (self.tile_size, self.tile_size):
            raise GoldManifestError(
                f"tile {t['tile_id']} mask shape {msk.shape} != "
                f"({self.tile_size},{self.tile_size})"
            )
        return img, msk

    def __getitem__(self, idx: int):
        if self._cache is not None and idx in self._cache:
            img, msk = self._cache[idx]
        else:
            img, msk = self._load_raw(idx)
            if self._cache is not None:
                self._cache[idx] = (img, msk)

        image = torch.from_numpy(np.ascontiguousarray(img, dtype=np.float32))
        mask = torch.from_numpy(np.ascontiguousarray(msk)).long()

        if not self.return_meta:
            return image, mask
        t = self.tiles[idx]
        return image, mask, {
            "tile_id": t["tile_id"],
            "scene_id": t["scene_id"],
            "source": t["source"],
            "split": t["split"],
        }

    # ------------------------------------------------------------------ #
    def oil_positive_flags(self) -> np.ndarray:
        """Per-tile boolean: does this tile contain at least one OIL pixel?

        Sampling policy is intentionally separate from dataset membership -
        every manifested tile stays addressable regardless of how it is sampled.
        """
        return np.array([t["oil_px"] > 0 for t in self.tiles], dtype=bool)

    def sampler_weights(self, positive_weight: float = 3.0) -> np.ndarray:
        pos = self.oil_positive_flags()
        w = np.ones(len(pos), dtype=np.float64)
        w[pos] = positive_weight
        return w

    def describe(self) -> dict[str, Any]:
        pos = self.oil_positive_flags()
        oil_px = sum(t["oil_px"] for t in self.tiles)
        total_px = len(self.tiles) * self.tile_size * self.tile_size
        by_source: dict[str, int] = {}
        for t in self.tiles:
            by_source[t["source"]] = by_source.get(t["source"], 0) + 1
        return {
            "dataset_version": self.dataset_version,
            "manifest_hash": self.manifest_hash,
            "split": self.split,
            "n_tiles": len(self.tiles),
            "n_scenes": len(self.scene_ids),
            "n_positive_tiles": int(pos.sum()),
            "n_empty_tiles": int((~pos).sum()),
            "oil_pixel_frac": oil_px / total_px if total_px else 0.0,
            "tiles_by_source": by_source,
        }
