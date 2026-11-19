import pytest
from pathlib import Path
import json
from datetime import datetime, timezone

from varuna_contracts.schemas import BBox, VesselTrack
from varuna_source_adapters.protocol import SourceQuery
from varuna_source_adapters.service import AdapterRegistry
from varuna_source_adapters.mock_cmems import MockCmemsAdapter
from varuna_source_adapters.mock_ais import MockAisAdapter

def test_mock_cmems_returns_valid_fetch_result():
    adapter = MockCmemsAdapter()
    query = SourceQuery(
        bbox=BBox(min_lon=70.0, min_lat=10.0, max_lon=75.0, max_lat=15.0),
        time_start=datetime.now(timezone.utc),
        time_end=datetime.now(timezone.utc),
        product_id="cmems_current"
    )
    result = adapter.fetch(query)
    assert result.is_simulated is True
    assert result.provenance.source_id == "cmems.mock"
    assert Path(result.artifact_path).exists()

def test_mock_ais_returns_valid_tracks():
    adapter = MockAisAdapter()
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    query = SourceQuery(
        bbox=BBox(min_lon=70.0, min_lat=10.0, max_lon=75.0, max_lat=15.0),
        time_start=now,
        time_end=now + timedelta(hours=2),
        product_id="ais_tracks"
    )
    result = adapter.fetch(query)
    
    with open(result.artifact_path, "r") as f:
        data = json.load(f)
    
    assert isinstance(data, list)
    for t in data:
        # Pydantic validation
        VesselTrack.model_validate(t)

def test_adapter_registry_rejects_unknown_product():
    registry = AdapterRegistry.create_mock()
    query = SourceQuery(
        bbox=BBox(min_lon=70.0, min_lat=10.0, max_lon=75.0, max_lat=15.0),
        time_start=datetime.now(timezone.utc),
        time_end=datetime.now(timezone.utc),
        product_id="nonexistent"
    )
    with pytest.raises(ValueError):
        registry.fetch("nonexistent", query)

def test_adapter_registry_health_all_true():
    registry = AdapterRegistry.create_mock()
    health = registry.health()
    assert all(health.values())
