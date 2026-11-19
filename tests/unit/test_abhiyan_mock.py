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


def test_abhiyan_full_gate_state_matrix():
    """
    Track 2 final integration, Task 8: ABHIYAN may only operate within
    ValidityGate policy. VALID and DEGRADED both allow operational
    tasking (ValidityState.allows_operational_action's own definition);
    RESTRICTED and INCONCLUSIVE never reach the Action Gateway
    (ValidityState's own docstring: "RESTRICTED -- analysis only, never
    reaches Action Gateway"); an absent gate result (gate_state=None,
    i.e. the gate has not produced anything -- the UNAVAILABLE case) is
    treated identically to a blocking state, not permissively.
    """
    service = AbhiyanService(MockAbhiyanProvider())
    env = _make_test_envelope()
    boxes = [SearchBox(
        bbox=BBox(min_lon=70, min_lat=10, max_lon=71, max_lat=11),
        center=GeoPoint(lon=70.5, lat=10.5),
        area_km2=100.0,
        phi_mass_contained=0.9
    )]

    taskings, _ = service.plan_mission(boxes, [AssetType.DORNIER], ValidityState.VALID, env, "CASE-01")
    assert len(taskings) == 1

    taskings, _ = service.plan_mission(boxes, [AssetType.DORNIER], ValidityState.DEGRADED, env, "CASE-01")
    assert len(taskings) == 1  # DEGRADED still allows operational action, with caveats surfaced elsewhere

    taskings, _ = service.plan_mission(boxes, [AssetType.DORNIER], ValidityState.RESTRICTED, env, "CASE-01")
    assert len(taskings) == 0

    taskings, _ = service.plan_mission(boxes, [AssetType.DORNIER], ValidityState.INCONCLUSIVE, env, "CASE-01")
    assert len(taskings) == 0

    # gate_state=None: the validity gate produced nothing at all (the
    # "UNAVAILABLE" case in the master-prompt vocabulary -- there is no
    # literal ValidityState.UNAVAILABLE member). Must not be treated as
    # permissive by a missing-argument default.
    taskings, _ = service.plan_mission(boxes, [AssetType.DORNIER], None, env, "CASE-01")
    assert len(taskings) == 0
