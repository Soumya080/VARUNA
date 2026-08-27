from typing import List, Tuple
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.quality import DedupState, DedupVerdict

class DedupPipeline:
    """Handles spatiotemporal deduplication across overlapping SAR swaths."""
    
    def process(self, artifacts: List[CanonicalSAR]) -> List[Tuple[CanonicalSAR, DedupState]]:
        # O(N^2) naive dedup for pipeline skeleton
        # In reality, would use R-tree or similar for spatio-temporal intersection
        results = []
        kept = []
        
        for sar in sorted(artifacts, key=lambda s: s.acquisition_time):
            is_dup = False
            duplicate_of = None
            
            for k in kept:
                # Same sensor and platform
                if sar.sensor == k.sensor and sar.platform == k.platform:
                    # Close in time (e.g. within 1 minute)
                    time_diff = abs((sar.acquisition_time - k.acquisition_time).total_seconds())
                    if time_diff < 60:
                        # Check spatial overlap (simple bounding box check)
                        if (sar.bbox.min_lon <= k.bbox.max_lon and sar.bbox.max_lon >= k.bbox.min_lon and
                            sar.bbox.min_lat <= k.bbox.max_lat and sar.bbox.max_lat >= k.bbox.min_lat):
                            is_dup = True
                            duplicate_of = k.scene_id
                            break
                            
            if is_dup:
                state = DedupState(verdict=DedupVerdict.DUPLICATE, duplicate_of=duplicate_of, reason="Spatio-temporal overlap")
                results.append((sar, state))
            else:
                kept.append(sar)
                state = DedupState(verdict=DedupVerdict.KEEP)
                results.append((sar, state))
                
        return results
