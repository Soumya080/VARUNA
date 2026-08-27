"""Abstraction for supplying per-channel pixel arrays to the normalization
step. Exists so FullPipeline never has to fabricate placeholder data
(zeros, empty dicts) and call it "training statistics" — every array that
feeds Normalizer.compute_stats must come from somewhere real (synthetic
generator or actual files), and that somewhere must be explicit and
swappable.
"""
from abc import ABC, abstractmethod
from typing import Dict
import os
import numpy as np

from varuna_data_eng.schemas.canonical_sar import CanonicalSAR


class TrainingArrayProvider(ABC):
    """Supplies per-channel numpy arrays for one scene.

    Callers (FullPipeline) are responsible for only invoking this on
    entries whose `split == "train"` — the provider itself is split-unaware
    by design, so that responsibility can't leak into a component that
    doesn't have the manifest context.
    """

    @abstractmethod
    def load_channels(self, sar: CanonicalSAR) -> Dict[str, np.ndarray]:
        """Return {channel_name: array} for one scene."""
        ...


class DeterministicSyntheticArrayProvider(TrainingArrayProvider):
    """Synthetic-mode only. Produces seeded, reproducible arrays — never to
    be confused with, or claimed as, real sensor data.
    """

    def __init__(self, seed: int = 42, shape: tuple = (64, 64)):
        self.seed = seed
        self.shape = shape

    def load_channels(self, sar: CanonicalSAR) -> Dict[str, np.ndarray]:
        channel_names = list(sar.channels.keys()) or ["VV"]
        out: Dict[str, np.ndarray] = {}
        for ch in channel_names:
            # Deterministic per (seed, scene, channel) so re-runs reproduce
            # identical statistics, but different scenes/channels don't
            # collapse onto the same array.
            local_seed = (self.seed + hash(f"{sar.scene_id}_{ch}")) % (2**32)
            rng = np.random.default_rng(local_seed)
            out[ch] = rng.standard_normal(self.shape).astype(np.float32)
        return out


class FileBackedArrayProvider(TrainingArrayProvider):
    """Loads real per-channel arrays from disk: `<data_path stem>.<channel>.npy`
    next to the scene's data_path.

    Fails loudly when a real array is not available rather than silently
    substituting placeholder data — consistent with the architecture's
    fail-safe invariant (no swallowed exceptions, no silent defaults).
    """

    def load_channels(self, sar: CanonicalSAR) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        base, _ = os.path.splitext(sar.data_path)
        for ch in sar.channels:
            path = f"{base}.{ch}.npy"
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"No training array available for channel '{ch}' of scene "
                    f"{sar.scene_id} at {path}. Real-mode normalization requires "
                    f"actual per-channel arrays; refusing to substitute placeholder data."
                )
            out[ch] = np.load(path)
        return out
