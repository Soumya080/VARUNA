import pytest
from varuna_abhiyan.optimizer import TaskingOptimizer
from varuna_contracts.schemas import AssetType, SearchBox, BBox, GeoPoint
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode

def test_tasking_optimizer():
    optimizer = TaskingOptimizer()
    
    box = SearchBox(
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        center=GeoPoint(lon=0.5, lat=0.5),
        area_km2=100.0,
        phi_mass_contained=0.8
    )
    
    env = EvidenceEnvelope(
        artifact_id="test",
        produced_by="test",
        provenance={"source_id": "test"},
        mode=EvidenceMode.SIMULATED,
    )
    
    taskings = optimizer.generate_tasking([box], [AssetType.DORNIER], env)
    
    assert len(taskings) == 1
    assert taskings[0].asset_type == AssetType.DORNIER
    assert taskings[0].search_box == box
