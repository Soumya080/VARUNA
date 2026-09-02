"""
STEP 7, Phase 4: the full authorization test matrix, driven by REAL
`POST /v1/auth/login`-issued tokens end to end through the real API —
not `dependency_overrides` (that already existed for STEP 6; this proves
the whole chain including JWT issuance and verification, not just the
principal-resolution boundary tested in test_api_security.py).
"""
from datetime import timedelta

from fastapi.testclient import TestClient

from apps.api.config import settings
from apps.api.main import app
from varuna_contracts.schemas import AssetTasking, BBox, GeoPoint, SearchBox
from varuna_infra.auth import create_access_token

client = TestClient(app)

# Per-test isolation of the alert/mission singletons is provided by the
# autouse fixture in tests/api/conftest.py.


def _login(username: str, password: str) -> str:
    r = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fresh_alert() -> str:
    client.get("/v1/replay/CASE-VALID")
    items = client.get("/v1/cases/REPLAY-CASE-VALID/alerts").json()["items"]
    # Pick one still in a state that accepts acknowledge/escalate.
    actionable = [i for i in items
                  if i["status"] in ("created", "routed", "delivery_pending", "delivered")]
    return (actionable or items)[0]["alert_id"]


def _fresh_mission():
    from apps.api.dependencies import get_mission_service
    tasking = AssetTasking(
        asset_type="dornier", base_name="Base",
        search_box=SearchBox(bbox=BBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1),
                              center=GeoPoint(lon=0.5, lat=0.5),
                              area_km2=1.0, phi_mass_contained=1.0),
        pattern="expanding_square", launch_time="2026-01-01T00:00:00Z",
        flight_hours=1.0, probability_of_detection=0.5, rationale="test",
    )
    return get_mission_service().create_mission(
        case_id="CASE-AUTH-MATRIX", asset_id="Asset-1", tasking=tasking)


# ------------------------------------------------- alert acknowledge matrix

def test_unauthenticated_acknowledge_is_401():
    alert_id = _fresh_alert()
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge")
    assert r.status_code == 401


def test_authenticated_but_unauthorized_acknowledge_is_403_and_leaves_state_unchanged():
    alert_id = _fresh_alert()
    token = _login("viewer", "viewer-demo-pass")  # read_only holds no alert permissions
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge", headers=_auth(token))
    assert r.status_code == 403

    detail = client.get(f"/v1/alerts/{alert_id}").json()
    assert detail["status"] not in ("acknowledged", "escalated", "resolved")
    assert detail["acknowledged_by"] is None


def test_authorized_role_acknowledges_successfully():
    alert_id = _fresh_alert()
    token = _login("officer", "officer-demo-pass")
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "acknowledged"
    assert r.json()["acknowledged_by"] == "officer"


def test_analyst_can_acknowledge_but_cannot_escalate():
    alert_id = _fresh_alert()
    token = _login("analyst", "analyst-demo-pass")
    ack = client.post(f"/v1/alerts/{alert_id}/acknowledge", headers=_auth(token))
    assert ack.status_code == 200
    esc = client.post(f"/v1/alerts/{alert_id}/escalate", headers=_auth(token))
    assert esc.status_code == 403


# ----------------------------------------------------- mission approve matrix

def test_unauthenticated_mission_approve_is_401():
    mission = _fresh_mission()
    r = client.post(f"/v1/missions/{mission.mission_id}/approve", json={"approved_by": "x"})
    assert r.status_code == 401


def test_authenticated_but_unauthorized_mission_approve_is_403_and_state_unchanged():
    mission = _fresh_mission()
    token = _login("analyst", "analyst-demo-pass")  # analyst holds no APPROVE_MISSION
    r = client.post(f"/v1/missions/{mission.mission_id}/approve",
                     json={"approved_by": "analyst"}, headers=_auth(token))
    assert r.status_code == 403

    fetched = client.get(f"/v1/missions/{mission.mission_id}").json()
    assert fetched["state"] == "available"
    assert fetched["human_approved_by"] is None


def test_authorized_duty_officer_approves_mission_and_it_is_audited():
    mission = _fresh_mission()
    token = _login("officer", "officer-demo-pass")
    r = client.post(f"/v1/missions/{mission.mission_id}/approve",
                     json={"approved_by": "officer"}, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["state"] == "assigned"
    assert r.json()["human_approved_by"] == "officer"

    audit = client.get(f"/v1/missions/{mission.mission_id}/audit").json()["items"]
    assert any(e["allowed"] and e["principal_id"] == "officer" for e in audit)


def test_mission_assigned_alert_is_raised_on_real_approval():
    """STEP 7, Phase 5: mission.assigned now fires a real, listable alert."""
    mission = _fresh_mission()
    token = _login("officer", "officer-demo-pass")
    client.post(f"/v1/missions/{mission.mission_id}/approve",
                json={"approved_by": "officer"}, headers=_auth(token))

    alerts = client.get(f"/v1/cases/{mission.case_id}/alerts").json()["items"]
    assert any(a["event_type"] == "mission.assigned" for a in alerts)


# ----------------------------------------------------------- system principal

def test_system_principal_is_denied_mission_approval_per_existing_policy():
    """Not a new rule — re-verifies through the full JWT path that a token
    minted for role="system" (which no login account maps to, but which the
    JWT layer itself does not forbid encoding) is still refused, because
    ROLE_PERMISSIONS never grants SYSTEM the human-approval permission."""
    mission = _fresh_mission()
    token = create_access_token(
        user_id="system", role="system",
        secret_key=settings.jwt_secret_key, expires_delta=timedelta(minutes=5),
    )
    r = client.post(f"/v1/missions/{mission.mission_id}/approve",
                     json={"approved_by": "system"}, headers=_auth(token))
    assert r.status_code == 403


# --------------------------------------------------------- JWT edge cases

def test_expired_token_is_401_not_500():
    token = create_access_token(
        user_id="officer", role="duty_officer",
        secret_key=settings.jwt_secret_key, expires_delta=timedelta(seconds=-1),
    )
    alert_id = _fresh_alert()
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge", headers=_auth(token))
    assert r.status_code == 401


def test_malformed_token_is_401_not_500():
    alert_id = _fresh_alert()
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge",
                     headers={"Authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


def test_tampered_token_is_401_not_500():
    token = _login("officer", "officer-demo-pass")
    tampered = token[:-6] + ("Z" * 6)
    alert_id = _fresh_alert()
    r = client.post(f"/v1/alerts/{alert_id}/acknowledge", headers=_auth(tampered))
    assert r.status_code == 401
