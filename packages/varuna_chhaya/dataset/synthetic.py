from typing import List, Any
from datetime import datetime, timezone, timedelta
import numpy as np
import tempfile
import os

from .schema import ChhayaSample
from .interface import ChhayaDatasetProvider

class SyntheticChhayaDataset(ChhayaDatasetProvider):
    def __init__(self, num_samples: int = 50, seq_len: int = 72, seed: int = 42):
        self.num_samples = num_samples
        self.seq_len = seq_len
        self.seed = seed
        self.temp_dir = tempfile.mkdtemp(prefix="chhaya_synthetic_")
        self.samples = []
        self._generate()
        
    def _generate(self):
        rng = np.random.RandomState(self.seed)
        
        for i in range(self.num_samples):
            sample_id = f"synth_{i:04d}"
            traj_id = f"traj_{i:04d}"
            
            # Generate fake trajectory data: [T, 4] for lon, lat, u, v
            trajectory_data = rng.randn(self.seq_len, 4).astype(np.float32)
            traj_path = os.path.join(self.temp_dir, f"{sample_id}_traj.npy")
            np.save(traj_path, trajectory_data)
            
            start_time = datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 365))
            
            sample = ChhayaSample(
                sample_id=sample_id,
                trajectory_id=traj_id,
                trajectory_path=traj_path,
                start_time=start_time,
                end_time=start_time + timedelta(hours=self.seq_len),
                metadata={"synthetic": True}
            )
            self.samples.append(sample)
            
    def load_sample(self, sample_id: str) -> ChhayaSample:
        for s in self.samples:
            if s.sample_id == sample_id:
                return s
        raise KeyError(f"Sample {sample_id} not found")
        
    def list_samples(self, split: str = "all") -> List[ChhayaSample]:
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
        return {"dataset_name": "synthetic_chhaya", "version": "v1.0.0"}
