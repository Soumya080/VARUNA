"""Phase 4 — real Asset/Personnel registry, and the previously-missing
POST /v1/missions. Uses a per-process isolated state dir (via VARUNA_STATE_DIR,
set globally in tests/conftest.py if present, or falls back to whatever the
running process already resolved) so this doesn't collide with a live demo's
persisted asset/mission state.
"""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _login(u: str, p: str) -> dict:
    r = client.post("/v1/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_asset_list_returns_seeded_fleet():
    r = client.get("/v1/assets")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 9
    ids = {a["asset_id"] for a in items}
    assert "ICGS-VARAD" in ids
    assert "PV-01-INTERCEPTOR" in ids


def test_available_filter_excludes_deployed_and_maintenance():
    r = client.get("/v1/assets?status=available")
    items = r.json()["items"]
    statuses = {a["status"] for a in items}
    assert statuses <= {"available"}
    ids = {a["asset_id"] for a in items}
    assert "ICGS-VARAD" not in ids       # deployed
    assert "PV-05-FAST-PATROL" not in ids  # maintenance


def test_get_single_asset_404_for_unknown():
    r = client.get("/v1/assets/NOT-A-REAL-ASSET")
    assert r.status_code == 404


def test_personnel_on_duty_filter():
    r = client.get("/v1/personnel?on_duty_only=true&role=duty_officer")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(p["on_duty"] for p in items)
    assert all(p["role"] == "duty_officer" for p in items)
    # DO-KOCHI-01 is seeded off-duty and must not appear.
    assert "DO-KOCHI-01" not in {p["personnel_id"] for p in items}


def test_personnel_seed_is_illustrative_indian_coast_guard_convention():
    r = client.get("/v1/personnel")
    names = {p["name"] for p in r.json()["items"]}
    assert any("Cdr." in n or "Cdt." in n for n in names)


def test_create_mission_requires_authentication():
    r = client.post("/v1/missions", json={"case_id": "X", "asset_id": "PV-01-INTERCEPTOR"})
    assert r.status_code == 401


def test_create_mission_with_available_asset_succeeds():
    headers = _login("admin", "admin-demo-pass")
    client.post("/v1/cases", json={"case_id": "CASE-MSN-A"}, headers=headers)
    r = client.post("/v1/missions", json={
        "case_id": "CASE-MSN-A", "asset_id": "PV-03-INTERCEPTOR",
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["case_id"] == "CASE-MSN-A"
    assert body["asset_id"] == "PV-03-INTERCEPTOR"
    assert body["state"] == "available"  # PROPOSED, not yet approved


def test_create_mission_against_unavailable_asset_is_409():
    headers = _login("admin", "admin-demo-pass")
    client.post("/v1/cases", json={"case_id": "CASE-MSN-B"}, headers=headers)
    r = client.post("/v1/missions", json={
        "case_id": "CASE-MSN-B", "asset_id": "ICGS-VARAD",  # seeded DEPLOYED
    }, headers=headers)
    assert r.status_code == 409


def test_create_mission_against_unknown_asset_is_404():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/missions", json={
        "case_id": "CASE-MSN-C", "asset_id": "DOES-NOT-EXIST",
    }, headers=headers)
    assert r.status_code == 404


def test_field_operator_cannot_create_mission():
    headers = _login("field", "field-demo-pass")
    r = client.post("/v1/missions", json={
        "case_id": "CASE-MSN-D", "asset_id": "PV-01-INTERCEPTOR",
    }, headers=headers)
    assert r.status_code == 403


def test_created_mission_flows_into_the_existing_approve_endpoint():
    """Full create -> approve lifecycle, proving the new endpoint composes
    with the pre-existing, unmodified mission FSM."""
    headers = _login("admin", "admin-demo-pass")
    client.post("/v1/cases", json={"case_id": "CASE-MSN-E"}, headers=headers)
    created = client.post("/v1/missions", json={
        "case_id": "CASE-MSN-E", "asset_id": "AIRCRAFT-02",
    }, headers=headers).json()
    mission_id = created["mission_id"]

    approved = client.post(
        f"/v1/missions/{mission_id}/approve",
        json={"approved_by": "admin"}, headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "assigned"
