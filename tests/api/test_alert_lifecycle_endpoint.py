"""
STEP 6: end-to-end alert lifecycle through the real API — CASE-VALID
replay -> GoldenCaseWorkflow -> alert correlation -> lifecycle endpoints.
"""
from fastapi.testclient import TestClient

from apps.api.dependencies import get_alert_lifecycle_service, get_mission_service
from apps.api.main import app
from apps.api.security import get_principal
from varuna_contracts.schemas import AssetTasking, BBox, GeoPoint, SearchBox
from varuna_infra.authorization import Principal

client = TestClient(app)


def _as(principal_id: str, role: str):
    return lambda: Principal(principal_id=principal_id, role=role)


def teardown_function(_fn):
    app.dependency_overrides.pop(get_principal, None)


def test_case_valid_replay_produces_one_listable_alert():
    r = client.get("/v1/replay/CASE-VALID")
    assert r.status_code == 200
    # case_id is deterministic per the replay route's own convention
    case_id = "REPLAY-CASE-VALID"

    listing = client.get(f"/v1/cases/{case_id}/alerts")
    assert listing.status_code == 200
    items = listing.json()["items"]
    # Workstream A: the Alert Orchestrator emits one alert per MATERIAL
    # DIMENSION that changed, so CASE-VALID yields several (detection
    # presence, attribution, validity, landfall) rather than the single
    # delivery-receipt alert the retired legacy path produced.
    assert len(items) >= 1
    assert all(i["case_id"] == case_id for i in items)
    dims = {i["material_dimension"] for i in items}
    assert "detection.presence" in dims
    assert all(i["is_simulated"] is True for i in items)  # replay never claims real delivery


def test_acknowledge_requires_authorization_and_is_denied_for_read_only():
    client.get("/v1/replay/CASE-VALID")
    alert_id = client.get("/v1/cases/REPLAY-CASE-VALID/alerts").json()["items"][0]["alert_id"]

    app.dependency_overrides[get_principal] = _as("viewer-1", "read_only")
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge")
    assert r.status_code == 403

    # Unchanged after denial. The orchestrator drives an alert to
    # 'delivered' on creation, so assert it did NOT advance to an
    # operator-handled state rather than asserting a literal 'created'.
    detail = client.get(f"/v1/alerts/{alert_id}")
    assert detail.json()["status"] not in ("acknowledged", "escalated", "resolved")
    assert detail.json()["acknowledged_by"] is None


def test_acknowledge_then_escalate_then_resolve_lifecycle():
    client.get("/v1/replay/CASE-VALID")
    alert_id = client.get("/v1/cases/REPLAY-CASE-VALID/alerts").json()["items"][0]["alert_id"]

    app.dependency_overrides[get_principal] = _as("officer-1", "duty_officer")
    ack = client.post(f"/v1/alerts/{alert_id}/acknowledge")
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    assert ack.json()["acknowledged_by"] == "officer-1"

    esc = client.post(f"/v1/alerts/{alert_id}/escalate")
    assert esc.status_code == 200
    assert esc.json()["status"] == "escalated"

    res = client.post(f"/v1/alerts/{alert_id}/resolve")
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"


def test_unknown_alert_id_is_404():
    app.dependency_overrides[get_principal] = _as("officer-1", "duty_officer")
    r = client.post("/v1/alerts/ALT-DOES-NOT-EXIST/acknowledge")
    assert r.status_code == 404


def test_mission_audit_persists_across_requests():
    """Regression for the fixed bug: get_mission_service() must be a
    singleton, so an authorization decision from one request is still
    visible in the next."""
    svc = get_mission_service()
    tasking = AssetTasking(
        asset_type="dornier", base_name="Base",
        search_box=SearchBox(
            bbox=BBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1),
            center=GeoPoint(lon=0.5, lat=0.5),
            area_km2=1.0, phi_mass_contained=1.0),
        pattern="expanding_square", launch_time="2026-01-01T00:00:00Z",
        flight_hours=1.0, probability_of_detection=0.5, rationale="test",
    )
    mission = svc.create_mission(case_id="CASE-AUDIT-TEST", asset_id="Asset-1", tasking=tasking)

    app.dependency_overrides[get_principal] = _as("viewer-1", "read_only")
    denied = client.post(f"/v1/missions/{mission.mission_id}/approve",
                          json={"approved_by": "viewer-1"})
    assert denied.status_code == 403

    audit = client.get(f"/v1/missions/{mission.mission_id}/audit")
    assert audit.status_code == 200
    entries = audit.json()["items"]
    assert len(entries) >= 1
    assert any(not e["allowed"] for e in entries)
