from varuna_infra.authorization import Principal
import pytest
from datetime import datetime, timezone
from varuna_contracts.schemas import AssetTasking, AssetType, SearchBox, BBox, GeoPoint
from varuna_contracts.states import MissionState, MissionRecord
from varuna_missions.repository import InMemoryMissionRepository
from varuna_missions.service import MissionService

def _make_dummy_tasking() -> AssetTasking:
    return AssetTasking(
        asset_type=AssetType.DORNIER,
        base_name="Base 1",
        search_box=SearchBox(
            bbox=BBox(min_lon=70, min_lat=10, max_lon=71, max_lat=11),
            center=GeoPoint(lon=70.5, lat=10.5),
            area_km2=100.0,
            phi_mass_contained=0.9
        ),
        pattern="expanding_square",
        launch_time=datetime.now(timezone.utc),
        flight_hours=4.0,
        probability_of_detection=0.85,
        rationale="test"
    )

def test_full_fsm_happy_path():
    svc = MissionService(InMemoryMissionRepository())
    m = svc.create_mission("CASE-1", "DORNIER-01", _make_dummy_tasking())
    svc.reserve(m.mission_id)
    svc.approve_and_assign(
        m.mission_id, approved_by="officer_123",
        principal=Principal(principal_id="officer_123", role="duty_officer"))
    svc.transition(m.mission_id, MissionState.ACKNOWLEDGED)
    svc.transition(m.mission_id, MissionState.EN_ROUTE)
    svc.transition(m.mission_id, MissionState.ON_STATION)
    svc.transition(m.mission_id, MissionState.SEARCHING)
    svc.transition(m.mission_id, MissionState.CONTACT)
    svc.transition(m.mission_id, MissionState.CONFIRMED)
    svc.transition(m.mission_id, MissionState.COMPLETE)
    svc.transition(m.mission_id, MissionState.CLOSED)
    
    final_m = svc.get(m.mission_id)
    assert final_m is not None
    assert final_m.state == MissionState.CLOSED

def test_assign_without_approval_raises():
    """Threat O-02: authorization gate."""
    svc = MissionService(InMemoryMissionRepository())
    m = svc.create_mission("CASE-1", "DORNIER-01", _make_dummy_tasking())
    svc.reserve(m.mission_id)
    with pytest.raises(ValueError, match="ASSIGNED requires human_approved_by"):
        svc.transition(m.mission_id, MissionState.ASSIGNED)
