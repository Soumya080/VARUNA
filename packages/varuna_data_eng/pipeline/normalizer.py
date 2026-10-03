import numpy as np
from typing import Dict, List
from datetime import datetime, timezone
import hashlib
from varuna_data_eng.schemas.normalization import NormalizationRecord, ChannelStats

class Normalizer:
    """Computes dataset-wide statistics across the train split and applies them."""
    
    def compute_stats(self, dataset_version: str, sensor: str, train_arrays: Dict[str, np.ndarray]) -> NormalizationRecord:
        """Computes stats. Mocked for pipeline layout."""
        # Calculate stats
        channels = {}
        for ch_name, arr in train_arrays.items():
            channels[ch_name] = ChannelStats(
                mean=float(np.mean(arr)),
                std=float(np.std(arr)),
                min=float(np.min(arr)),
                max=float(np.max(arr)),
                p2=float(np.percentile(arr, 2)),
                p98=float(np.percentile(arr, 98))
            )
            
        return NormalizationRecord(
            dataset_version=dataset_version,
            sensor=sensor,
            channels=channels,
            method="standard_p2_p98",
            computed_from_split="train",
            n_samples=len(train_arrays),
            computed_at=datetime.now(timezone.utc),
            checksum=hashlib.md5(f"{dataset_version}_{sensor}".encode()).hexdigest()
        )
        
    def apply(self, arr: np.ndarray, channel_name: str, record: NormalizationRecord) -> np.ndarray:
        """Applies normalization (e.g., standard clipping and scaling)."""
        stats = record.channels.get(channel_name)
        if not stats:
            raise ValueError(f"No stats for channel {channel_name}")
            
        # Clip to p2/p98 and scale 0-1
        arr = np.clip(arr, stats.p2, stats.p98)
        arr = (arr - stats.p2) / (stats.p98 - stats.p2 + 1e-8)
        return arr
