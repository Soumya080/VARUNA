from typing import List, Dict, Any
from datetime import datetime
from .manifest import DatasetSplit

class DatasetSplitter:
    @staticmethod
    def geographic_split(samples: List[Any], region_map: Dict[str, str], test_regions: List[str], val_regions: List[str]) -> DatasetSplit:
        """
        Splits dataset by geographic region to avoid spatial leakage.
        region_map is a dictionary mapping sample_id to region.
        """
        train_ids = []
        val_ids = []
        test_ids = []
        
        for sample in samples:
            sample_id = sample.sample_id
            region = region_map.get(sample_id)
            if region in test_regions:
                test_ids.append(sample_id)
            elif region in val_regions:
                val_ids.append(sample_id)
            else:
                train_ids.append(sample_id)
                
        return DatasetSplit(
            train_ids=train_ids,
            val_ids=val_ids,
            test_ids=test_ids,
            split_strategy="geographic",
            split_metadata={"test_regions": test_regions, "val_regions": val_regions}
        )
        
    @staticmethod
    def temporal_split(samples: List[Any], val_cutoff: datetime, test_cutoff: datetime) -> DatasetSplit:
        """
        Splits dataset by time to avoid temporal leakage.
        Assumes each sample has an acquisition_date property.
        """
        train_ids = []
        val_ids = []
        test_ids = []
        
        for sample in samples:
            sample_id = sample.sample_id
            date = sample.acquisition_date
            if date >= test_cutoff:
                test_ids.append(sample_id)
            elif date >= val_cutoff:
                val_ids.append(sample_id)
            else:
                train_ids.append(sample_id)
                
        return DatasetSplit(
            train_ids=train_ids,
            val_ids=val_ids,
            test_ids=test_ids,
            split_strategy="temporal",
            split_metadata={"val_cutoff": val_cutoff.isoformat(), "test_cutoff": test_cutoff.isoformat()}
        )

    @staticmethod
    def geographic_temporal_split(samples: List[Any], region_map: Dict[str, str], test_regions: List[str], val_cutoff: datetime, test_cutoff: datetime) -> DatasetSplit:
        # Simplistic implementation: Test data is drawn from test_regions OR after test_cutoff.
        train_ids = []
        val_ids = []
        test_ids = []
        
        for sample in samples:
            sample_id = sample.sample_id
            region = region_map.get(sample_id)
            date = sample.acquisition_date
            
            is_test_region = region in test_regions
            
            if is_test_region or date >= test_cutoff:
                test_ids.append(sample_id)
            elif date >= val_cutoff:
                val_ids.append(sample_id)
            else:
                train_ids.append(sample_id)
                
        return DatasetSplit(
            train_ids=train_ids,
            val_ids=val_ids,
            test_ids=test_ids,
            split_strategy="geographic_temporal",
            split_metadata={
                "test_regions": test_regions, 
                "val_cutoff": val_cutoff.isoformat(), 
                "test_cutoff": test_cutoff.isoformat()
            }
        )

    @staticmethod
    def validate_split(split: DatasetSplit, samples: List[Any]) -> List[str]:
        violations = []
        train_set = set(split.train_ids)
        val_set = set(split.val_ids)
        test_set = set(split.test_ids)
        
        # Check for intersection leakage
        if train_set.intersection(test_set):
            violations.append("Leakage: train and test sets overlap.")
        if train_set.intersection(val_set):
            violations.append("Leakage: train and val sets overlap.")
        if val_set.intersection(test_set):
            violations.append("Leakage: val and test sets overlap.")
            
        # We could also check spatial leakage (e.g., scene_id overlap)
        scene_map = {s.sample_id: getattr(s, "scene_id", None) for s in samples}
        
        train_scenes = {scene_map[sid] for sid in train_set if scene_map.get(sid)}
        test_scenes = {scene_map[sid] for sid in test_set if scene_map.get(sid)}
        
        if train_scenes.intersection(test_scenes):
            violations.append("Spatial Leakage: train and test sets share parent scenes.")
            
        return violations
