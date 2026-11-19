from typing import List, Dict
from varuna_data_eng.schemas.manifest import ManifestEntry

class SplitEngine:
    """Performs deterministic dataset splitting and outputs SplitManifest component."""
    
    VALID_STRATEGIES = ("hash_random", "scene_group", "geographic", "temporal", "geographic_temporal")

    def __init__(self, seed: int = 42, strategy: str = "hash_random"):
        if strategy not in self.VALID_STRATEGIES:
            raise ValueError(f"Unknown split strategy: {strategy}. Valid: {self.VALID_STRATEGIES}")
        self.seed = seed
        self.strategy = strategy

    def split(self, entries: List[ManifestEntry], train_ratio: float = 0.8, val_ratio: float = 0.1) -> Dict[str, List[ManifestEntry]]:
        """Assigns splits deterministically based on the chosen strategy.

        `hash_random` and `scene_group` both group by raw scene_id (no
        geography/time signal) — they are distinct names for the same
        random-by-scene behavior, kept separate for callers that want to be
        explicit about intent. They must never be reported as "spatial_block"
        or any strategy that implies geographic awareness.
        """
        import hashlib

        def group_key_for(entry: ManifestEntry) -> str:
            if self.strategy == "geographic":
                return entry.region
            if self.strategy == "temporal":
                return entry.acquisition_date.strftime("%Y-%m")
            if self.strategy == "geographic_temporal":
                return f"{entry.region}_{entry.acquisition_date.strftime('%Y-%m')}"
            return entry.scene_id  # hash_random / scene_group

        splits = {"train": [], "val": [], "test": []}
        if not entries:
            return splits

        group_keys = {group_key_for(e) for e in entries}
        if len(group_keys) <= 1:
            # A dataset with only one distinct group cannot be meaningfully
            # split (there is nothing to hold out that isn't identical, by
            # the chosen strategy's own definition, to what's kept). Rather
            # than gamble a whole degenerate dataset onto one arbitrary
            # split via the hash, route it entirely to train: you cannot
            # validate/test on data indistinguishable from your only
            # training group anyway.
            for entry in entries:
                entry.split = "train"
                splits["train"].append(entry)
            return splits

        for entry in entries:
            group_key = group_key_for(entry)

            # Deterministic hash of the group_key for splitting
            h = int(hashlib.md5(f"{group_key}_{self.seed}".encode()).hexdigest(), 16)
            fraction = (h % 10000) / 10000.0

            if fraction < train_ratio:
                entry.split = "train"
                splits["train"].append(entry)
            elif fraction < train_ratio + val_ratio:
                entry.split = "val"
                splits["val"].append(entry)
            else:
                entry.split = "test"
                splits["test"].append(entry)

        return splits
