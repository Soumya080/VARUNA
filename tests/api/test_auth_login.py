"""STEP 7: POST /v1/auth/login — the smallest real login path this
repository did not previously have."""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_login_with_valid_credentials_returns_a_usable_jwt():
    r = client.post("/v1/auth/login", json={"username": "officer", "password": "officer-demo-pass"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "duty_officer"
    assert body["token_type"] == "bearer"
    assert body["expires_in_seconds"] == 1800

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == {"principal_id": "officer", "role": "duty_officer"}


def test_login_with_wrong_password_is_401():
    r = client.post("/v1/auth/login", json={"username": "officer", "password": "wrong"})
    assert r.status_code == 401


def test_login_with_unknown_username_is_401_same_shape_as_wrong_password():
    unknown = client.post("/v1/auth/login", json={"username": "nobody", "password": "x"})
    wrong = client.post("/v1/auth/login", json={"username": "officer", "password": "wrong"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["message"] == wrong.json()["message"]


def test_client_cannot_supply_its_own_role():
    """The request body has no role field at all — this proves it, rather
    than merely asserting the schema, by sending one anyway and confirming
    it is ignored (rejected as an unknown field or simply has no effect)."""
    r = client.post(
        "/v1/auth/login",
        json={"username": "viewer", "password": "viewer-demo-pass", "role": "admin"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "read_only"  # server-side registry role, not "admin"


def test_every_repository_role_can_log_in():
    for username, password, expected_role in [
        ("admin", "admin-demo-pass", "admin"),
        ("officer", "officer-demo-pass", "duty_officer"),
        ("analyst", "analyst-demo-pass", "analyst"),
        ("field", "field-demo-pass", "field_operator"),
        ("viewer", "viewer-demo-pass", "read_only"),
    ]:
        r = client.post("/v1/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, username
        assert r.json()["role"] == expected_role


def test_me_without_a_token_is_401():
    r = client.get("/v1/auth/me")
    assert r.status_code == 401


def test_me_with_a_tampered_token_is_401():
    login = client.post("/v1/auth/login", json={"username": "officer", "password": "officer-demo-pass"})
    token = login.json()["access_token"]
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    r = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401
