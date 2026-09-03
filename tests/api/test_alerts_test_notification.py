"""POST /v1/alerts/test-notification — credential-verification endpoint.

Covers Phase 0a (WhatsApp/Zoho retired as channel names) and Phase 0b (the
endpoint honestly reports NOT_CONFIGURED, never fabricates SUCCESS, and is
admin-gated).
"""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _login(u: str, p: str) -> dict:
    r = client.post("/v1/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_requires_authentication():
    r = client.post("/v1/alerts/test-notification", json={"role": "duty_officer"})
    assert r.status_code in (401, 403)


def test_non_admin_role_is_forbidden():
    headers = _login("field", "field-demo-pass")
    r = client.post("/v1/alerts/test-notification", json={"role": "duty_officer"}, headers=headers)
    assert r.status_code == 403


def test_admin_gets_honest_not_configured_results():
    headers = _login("admin", "admin-demo-pass")
    r = client.post("/v1/alerts/test-notification", json={"role": "duty_officer"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["channels"]["email"] == "NOT_CONFIGURED"
    assert body["channels"]["sms"] in ("NOT_CONFIGURED", "REAL")
    assert "whatsapp" not in body["channels"]
    assert "zoho_cliq" not in body["channels"]
    for delivery in body["results"]:
        assert delivery["status"] != "DELIVERED" or delivery["channel"] == "dashboard"


def test_whatsapp_channel_name_is_rejected_not_silently_ignored():
    headers = _login("admin", "admin-demo-pass")
    r = client.post(
        "/v1/alerts/test-notification",
        json={"role": "duty_officer", "channels": ["email", "whatsapp"]},
        headers=headers,
    )
    assert r.status_code == 422
    assert "whatsapp" in r.text.lower()


def test_zoho_channel_name_is_rejected_not_silently_ignored():
    headers = _login("admin", "admin-demo-pass")
    r = client.post(
        "/v1/alerts/test-notification",
        json={"role": "duty_officer", "channels": ["zoho_cliq"]},
        headers=headers,
    )
    assert r.status_code == 422
