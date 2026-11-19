from typing import Dict, List, Any
from dataclasses import dataclass
from varuna_data_eng.schemas.manifest import ManifestEntry
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR

@dataclass
class LeakagePolicy:
    min_temporal_distance_days: float = 7.0
    min_geographic_distance_km: float = 50.0

class LeakageGuard:
    """Verifies that no test data leaked into train, spatially or temporally."""
    
    def __init__(self, policy: LeakagePolicy = None):
        self.policy = policy or LeakagePolicy()
        
    def _approx_distance_km(self, bbox1: Any, bbox2: Any) -> float:
        # Simple Euclidean approximation since we don't have pyproj imported here
        lat_diff = (bbox1.min_lat + bbox1.max_lat)/2.0 - (bbox2.min_lat + bbox2.max_lat)/2.0
        lon_diff = (bbox1.min_lon + bbox1.max_lon)/2.0 - (bbox2.min_lon + bbox2.max_lon)/2.0
        return ((lat_diff * 111.0)**2 + (lon_diff * 111.0)**2)**0.5
    
    SPLIT_NAMES = ("train", "val", "test")

    def check_leakage(self, splits: Dict[str, List[ManifestEntry]], sar_map: Dict[str, CanonicalSAR] = None) -> bool:
        """Applies the same identity + geo-temporal proximity policy to every
        pair of splits (train/val, train/test, val/test) — no split pair is
        exempt, and val is not just an ID-equality check.
        """
        id_sets = {name: {e.scene_id for e in splits.get(name, [])} for name in self.SPLIT_NAMES}
        pairs = [(a, b) for i, a in enumerate(self.SPLIT_NAMES) for b in self.SPLIT_NAMES[i + 1:]]

        # Prevent the same scene appearing in more than one split
        for a, b in pairs:
            if id_sets[a].intersection(id_sets[b]):
                return False

        if not sar_map:
            return True

        # Check temporal and spatial leakage for every split pair
        for a, b in pairs:
            for id_a in id_sets[a]:
                if id_a not in sar_map:
                    continue
                sar_a = sar_map[id_a]
                for id_b in id_sets[b]:
                    if id_b not in sar_map:
                        continue
                    sar_b = sar_map[id_b]

                    delta_days = abs((sar_a.acquisition_time - sar_b.acquisition_time).total_seconds()) / 86400.0
                    dist_km = self._approx_distance_km(sar_a.bbox, sar_b.bbox)

                    if delta_days < self.policy.min_temporal_distance_days and dist_km < self.policy.min_geographic_distance_km:
                        # Leaked! Too close in space AND time
                        return False

        return True
