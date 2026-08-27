import pytest
from datetime import datetime
from varuna_infra.dataset.splitter import DatasetSplitter

class MockSample:
    def __init__(self, sample_id, region, scene_id, date):
        self.sample_id = sample_id
        self.region = region
        self.scene_id = scene_id
        self.acquisition_date = date

def test_geographic_split():
    samples = [
        MockSample("s1", "A", "scene1", None),
        MockSample("s2", "B", "scene2", None),
        MockSample("s3", "C", "scene3", None),
        MockSample("s4", "A", "scene4", None),
    ]
    
    region_map = {s.sample_id: s.region for s in samples}
    split = DatasetSplitter.geographic_split(samples, region_map, test_regions=["C"], val_regions=["B"])
    
    assert "s3" in split.test_ids
    assert "s2" in split.val_ids
    assert "s1" in split.train_ids
    assert "s4" in split.train_ids

def test_validate_split_leakage():
    samples = [
        MockSample("s1", "A", "scene1", None),
        MockSample("s2", "A", "scene1", None),
    ]
    
    region_map = {s.sample_id: s.region for s in samples}
    split = DatasetSplitter.geographic_split(samples, region_map, test_regions=["C"], val_regions=["B"])
    
    # Introduce spatial leakage artificially
    split.test_ids.append("s2")
    
    violations = DatasetSplitter.validate_split(split, samples)
    assert len(violations) > 0
    assert any("Spatial Leakage" in v for v in violations)
