"""Phase 3 — real case-intake form. Every new field is optional: the
zero-detail one-click path must keep working exactly as before, and a caller
who supplies detail must see it round-trip verbatim into case.metadata."""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _login(u: str, p: str) -> dict:
    r = client.post("/v1/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_zero_field_post_still_creates_a_case():
    """The genuine one-click path — regression guard."""
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/cases", json={}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "created"
    # reported_by defaults to the authenticated principal — a case always
    # has a real reporter, even when the detail form was skipped.
    assert body["metadata"]["reported_by"] == "admin"


def test_optional_fields_round_trip_into_metadata():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/cases", json={
        "case_id": "CASE-INTAKE-TEST-1",
        "reported_by": "LT Cdr Rao",
        "initial_location": {"lon": 72.6, "lat": 18.9},
        "observation_source": "Coast Guard patrol report",
        "priority": "high",
        "notes": "Sheen observed near approach channel",
    }, headers=headers)
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["reported_by"] == "LT Cdr Rao"
    assert meta["initial_location"] == {"lon": 72.6, "lat": 18.9}
    assert meta["observation_source"] == "Coast Guard patrol report"
    assert meta["priority"] == "high"
    assert meta["notes"] == "Sheen observed near approach channel"


def test_partial_detail_is_accepted():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/cases", json={
        "case_id": "CASE-INTAKE-TEST-2",
        "observation_source": "public tip-off",
    }, headers=headers)
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["observation_source"] == "public tip-off"
    assert meta.get("initial_location") is None


def test_invalid_geopoint_is_rejected_with_422():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/cases", json={
        "case_id": "CASE-INTAKE-TEST-3",
        "initial_location": {"lon": 999, "lat": 18.9},
    }, headers=headers)
    assert r.status_code == 422


def test_duplicate_case_id_still_409s_with_detail_fields_present():
    headers = _login("admin", "admin-demo-pass")
    body = {"case_id": "CASE-INTAKE-TEST-4", "notes": "first"}
    r1 = client.post("/v1/cases", json=body, headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/v1/cases", json={**body, "notes": "second"}, headers=headers)
    assert r2.status_code == 409
