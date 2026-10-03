"""
VARUNA GRID — API Tests for Cases Router.

State-changing endpoints (create/ingest/reconstruct/attribute) now require an
authenticated `Principal` with `Permission.CREATE_CASE` /
`Permission.RUN_CASE_STAGE` (Phase 5, VARUNA_PRODUCT_READY hardening). The
happy-path tests below authenticate via a dependency override representing a
DUTY_OFFICER (the same role the mission-approval flow trusts) rather than
minting a real JWT for every call, since the router itself does not care how
`Principal` was produced. `test_authorization_enforcement.py` in
`tests/unit/` and the negative tests at the bottom of this file cover the
`get_principal` resolution logic (JWT verification, demo_mode gating) and
role-based denial directly.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.security import get_principal
from varuna_infra.authorization import Principal


@pytest.fixture
def client():
    def _duty_officer() -> Principal:
        return Principal(principal_id="test-duty-officer", role="duty_officer")

    app.dependency_overrides[get_principal] = _duty_officer
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_principal, None)


def test_create_case(client):
    response = client.post("/v1/cases", json={"case_id": "TEST-123"})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert data["status"] == "created"

def test_get_case(client):
    client.post("/v1/cases", json={"case_id": "TEST-123"})
    response = client.get("/v1/cases/TEST-123")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert data["status"] == "created"
    assert data["scientific_status"] == "EXPERIMENTAL / UNVALIDATED"

def test_ingest_case(client):
    client.post("/v1/cases", json={"case_id": "TEST-123"})
    response = client.post("/v1/cases/TEST-123/ingest", json={"use_fixture": "case_0001"})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert "guard_verdict" in data
    # CaseWorkflow.ingest() transitions INGESTING -> GUARDING before running
    # the guard, and there is no post-guard-success state until reconstruct()
    # is called, so "guarding" is the correct resting status on the accept
    # path (see packages/varuna_domain/case_workflow.py:65-90).
    assert data["status"] == "guarding"

def test_ingest_case_rejects_unknown_fixture(client):
    client.post("/v1/cases", json={"case_id": "TEST-BAD-FIXTURE"})
    response = client.post(
        "/v1/cases/TEST-BAD-FIXTURE/ingest",
        json={"use_fixture": "varuna_netra.dataset.gold"},
    )
    assert response.status_code == 400

def test_reconstruct_case(client):
    client.post("/v1/cases", json={"case_id": "TEST-123"})
    client.post("/v1/cases/TEST-123/ingest", json={"use_fixture": "case_0001"})
    response = client.post("/v1/cases/TEST-123/reconstruct", json={"seed": 42})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"

def test_attribute_case(client):
    client.post("/v1/cases", json={"case_id": "TEST-123"})
    client.post("/v1/cases/TEST-123/ingest", json={"use_fixture": "case_0001"})
    client.post("/v1/cases/TEST-123/reconstruct", json={"seed": 42})
    response = client.post("/v1/cases/TEST-123/attribute", json={"latent_prior": 0.5})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"

def test_get_phi_and_attribution(client):
    client.post("/v1/cases", json={"case_id": "TEST-123"})
    client.post("/v1/cases/TEST-123/ingest", json={"use_fixture": "case_0001"})
    client.post("/v1/cases/TEST-123/reconstruct", json={"seed": 42})
    client.post("/v1/cases/TEST-123/attribute", json={"latent_prior": 0.5})

    response = client.get("/v1/cases/TEST-123/phi")
    assert response.status_code == 200
    data = response.json()
    assert "phi_id" in data

    response = client.get("/v1/cases/TEST-123/attribution")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert data["scientific_status"] == "EXPERIMENTAL / UNVALIDATED"


# --------------------------------------------------------------------------
# Negative authorization tests (Phase 5, Phase 13): unauthenticated and
# under-privileged callers must not be able to mutate state.
# --------------------------------------------------------------------------

def test_create_case_without_auth_is_401():
    """No dependency override, no headers, demo_mode default False: the real
    `get_principal` resolver must reject this before the route body runs."""
    with TestClient(app) as unauth_client:
        response = unauth_client.post("/v1/cases", json={"case_id": "TEST-UNAUTH"})
    assert response.status_code == 401

def test_create_case_wrong_role_is_403():
    def _analyst() -> Principal:
        return Principal(principal_id="test-analyst", role="analyst")

    app.dependency_overrides[get_principal] = _analyst
    try:
        with TestClient(app) as c:
            response = c.post("/v1/cases", json={"case_id": "TEST-FORBIDDEN"})
    finally:
        app.dependency_overrides.pop(get_principal, None)
    assert response.status_code == 403

def test_ingest_wrong_role_is_403():
    def _read_only() -> Principal:
        return Principal(principal_id="test-readonly", role="read_only")

    def _duty_officer() -> Principal:
        return Principal(principal_id="test-duty-officer", role="duty_officer")

    app.dependency_overrides[get_principal] = _duty_officer
    try:
        with TestClient(app) as c:
            c.post("/v1/cases", json={"case_id": "TEST-INGEST-FORBIDDEN"})
    finally:
        app.dependency_overrides.pop(get_principal, None)

    app.dependency_overrides[get_principal] = _read_only
    try:
        with TestClient(app) as c:
            response = c.post(
                "/v1/cases/TEST-INGEST-FORBIDDEN/ingest",
                json={"use_fixture": "case_0001"},
            )
    finally:
        app.dependency_overrides.pop(get_principal, None)
    assert response.status_code == 403
