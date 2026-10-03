from typing import List, Any
from datetime import datetime, timezone, timedelta
import atexit
import numpy as np
import shutil
import tempfile
import os
import uuid

from .schema import NetraSample
from .interface import NetraDatasetProvider

class SyntheticNetraDataset(NetraDatasetProvider):
    """Generates real `.npy` tile/mask files under a temp directory so
    trainer/dataset code under test can do real disk I/O against realistic
    shapes, rather than mocking it away.

    Cleanup (Phase 4 fix, docs/product/HONESTY_LEDGER.md): this class used
    to `tempfile.mkdtemp()` and never remove the directory. Each instance
    with the default `num_samples=50` writes ~150MB of (3, 512, 512)
    float32 arrays; repeated test runs across a session accumulated tens of
    GB of orphaned temp data (observed: ~100GB from one day's test runs),
    which went on to cause unrelated, hard-to-diagnose disk-full failures
    elsewhere (torch checkpoint writes failing mid-save). `close()` removes
    the directory; it also runs automatically via `__del__` and an
    `atexit`-registered fallback, so a caller that forgets to call it
    explicitly (as the pre-existing tests did) still doesn't leak."""

    def __init__(self, num_samples: int = 50, seed: int = 42):
        self.num_samples = num_samples
        self.seed = seed
        self.temp_dir = tempfile.mkdtemp(prefix="netra_synthetic_")
        self.samples = []
        self._generate()
        self._closed = False
        # atexit backstop: covers the case where neither __del__ (which
        # CPython does not guarantee ever runs, e.g. on a hard interpreter
        # exit) nor an explicit close()/context-manager exit happens.
        atexit.register(SyntheticNetraDataset._cleanup_dir, self.temp_dir)

    @staticmethod
    def _cleanup_dir(path: str) -> None:
        shutil.rmtree(path, ignore_errors=True)

    def close(self) -> None:
        if not self._closed:
            self._cleanup_dir(self.temp_dir)
            self._closed = True

    def __enter__(self) -> "SyntheticNetraDataset":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        # Best-effort only — see class docstring on why atexit is the real
        # backstop, not this.
        try:
            self.close()
        except Exception:
            pass

    def _generate(self):
        rng = np.random.RandomState(self.seed)
        
        for i in range(self.num_samples):
            sample_id = f"synth_{i:04d}"
            scene_id = f"scene_{i // 10}"
            region = ["region_A", "region_B", "region_C"][i % 3]
            
            # Generate fake image (3 channels: VV, VH, Wind)
            image_data = rng.randn(3, 512, 512).astype(np.float32)
            tile_path = os.path.join(self.temp_dir, f"{sample_id}_img.npy")
            np.save(tile_path, image_data)
            
            # Generate fake mask (0=bg, 1=oil, 2=lookalike)
            mask_data = rng.randint(0, 3, size=(512, 512)).astype(np.uint8)
            mask_path = os.path.join(self.temp_dir, f"{sample_id}_mask.npy")
            np.save(mask_path, mask_data)
            
            sample = NetraSample(
                sample_id=sample_id,
                scene_id=scene_id,
                tile_path=tile_path,
                mask_path=mask_path,
                region=region,
                acquisition_date=datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 365)),
                wind_speed_ms=float(rng.uniform(2.0, 15.0)),
                metadata={"synthetic": True}
            )
            self.samples.append(sample)
            
    def load_sample(self, sample_id: str) -> NetraSample:
        for s in self.samples:
            if s.sample_id == sample_id:
                return s
        raise KeyError(f"Sample {sample_id} not found")
        
    def list_samples(self, split: str = "all") -> List[NetraSample]:
        # Simplistic split logic for synthetic dataset
        if split == "all":
            return self.samples
        elif split == "train":
            return self.samples[:int(self.num_samples * 0.7)]
        elif split == "val":
            return self.samples[int(self.num_samples * 0.7):int(self.num_samples * 0.85)]
        elif split == "test":
            return self.samples[int(self.num_samples * 0.85):]
        else:
            return self.samples
            
    def get_manifest(self) -> Any:
        return {"dataset_name": "synthetic_netra", "version": "v1.0.0"}
