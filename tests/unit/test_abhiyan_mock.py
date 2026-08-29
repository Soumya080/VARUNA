import pytest
from varuna_contracts.schemas import AssetType, SearchBox, BBox, GeoPoint
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, TrustState, ValidityState, QualityMetrics, Provenance
from varuna_abhiyan.mock import MockAbhiyanProvider
from varuna_abhiyan.service import AbhiyanService

def _make_test_envelope() -> EvidenceEnvelope:
    return EvidenceEnvelope(
        artifact_id="test-env-01",
        produced_by="test",
        trust=TrustState.TRUSTED,
        validity_state=ValidityState.VALID,
        quality=QualityMetrics(model_confidence=1.0),
        provenance=Provenance(source_id="test"),
        mode=EvidenceMode.SIMULATED,
    )

def test_abhiyan_returns_tasking():
    provider = MockAbhiyanProvider()
    env = _make_test_envelope()
    boxes = [SearchBox(
        bbox=BBox(min_lon=70, min_lat=10, max_lon=71, max_lat=11),
        center=GeoPoint(lon=70.5, lat=10.5),
        area_km2=100.0,
        phi_mass_contained=0.9
    )]
    taskings = provider.generate_tasking(boxes, [AssetType.DORNIER], env)
    assert len(taskings) == 1
    assert taskings[0].asset_type == AssetType.DORNIER
    assert taskings[0].base_name == "Port Blair"

def test_abhiyan_service_blocks_on_invalid_gate():
    service = AbhiyanService(MockAbhiyanProvider())
    env = _make_test_envelope()
    boxes = [SearchBox(
        bbox=BBox(min_lon=70, min_lat=10, max_lon=71, max_lat=11),
        center=GeoPoint(lon=70.5, lat=10.5),
        area_km2=100.0,
        phi_mass_contained=0.9
    )]
    
    # Gate restricts action
    taskings, out_env = service.plan_mission(boxes, [AssetType.DORNIER], ValidityState.RESTRICTED, env, "CASE-01")
    assert len(taskings) == 0
    
    # Gate allows action
    taskings, out_env = service.plan_mission(boxes, [AssetType.DORNIER], ValidityState.VALID, env, "CASE-01")
    assert len(taskings) == 1
