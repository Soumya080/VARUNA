"""Phase 7 — POST/GET /v1/cases/{case_id}/memory-feedback."""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _login(u: str, p: str) -> dict:
    r = client.post("/v1/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_requires_authentication():
    r = client.post("/v1/cases/CASE-X/memory-feedback", json={
        "retrieved_case_id": "PRIOR-1", "useful": True,
    })
    assert r.status_code == 401


def test_submit_and_list_round_trip():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/cases/CASE-FEEDBACK-TEST-1/memory-feedback", json={
        "retrieved_case_id": "PRIOR-1", "useful": True,
        "similarity_at_retrieval": 0.8,
        "components_at_retrieval": {"geography": 0.9, "environment": 0.4},
    }, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["recorded_by"] == "admin"
    assert body["useful"] is True

    listed = client.get("/v1/cases/CASE-FEEDBACK-TEST-1/memory-feedback")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(i["retrieved_case_id"] == "PRIOR-1" for i in items)


def test_blank_retrieved_case_id_is_rejected():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/cases/CASE-FEEDBACK-TEST-2/memory-feedback", json={
        "retrieved_case_id": "  ", "useful": False,
    }, headers=headers)
    assert r.status_code == 422


def test_feedback_for_one_case_does_not_leak_into_another():
    headers = _login("admin", "admin-demo-pass")
    client.post("/v1/cases/CASE-FEEDBACK-A/memory-feedback", json={
        "retrieved_case_id": "X", "useful": True,
    }, headers=headers)
    other = client.get("/v1/cases/CASE-FEEDBACK-B/memory-feedback")
    assert other.json()["items"] == []
