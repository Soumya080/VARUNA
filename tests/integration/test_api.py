import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.security import get_principal
from varuna_infra.authorization import Principal


@pytest.fixture
def client():
    from varuna_domain.repositories import InMemoryCaseRepository, InMemoryArtifactRepository, InMemoryEventStore
    from varuna_infra.inmemory_store import InMemoryObjectStore
    from apps.api.dependencies import get_case_repo, get_artifact_repo, get_event_repo, get_object_store

    cases = InMemoryCaseRepository()
    artifacts = InMemoryArtifactRepository()
    events = InMemoryEventStore()
    store = InMemoryObjectStore()

    def override_get_case_repo():
        return cases

    def override_get_artifact_repo():
        return artifacts

    def override_get_event_repo():
        return events

    def override_get_object_store():
        return store

    def override_get_principal() -> Principal:
        # State-changing routes require authorization as of Phase 5
        # (VARUNA_PRODUCT_READY hardening); this fixture exercises the
        # workflow logic under a role that holds every permission these
        # tests exercise, not the identity-resolution logic itself, which
        # `tests/api/test_cases.py` and `tests/unit/test_authorization_enforcement.py`
        # cover directly.
        return Principal(principal_id="test-duty-officer", role="duty_officer")

    app.dependency_overrides[get_case_repo] = override_get_case_repo
    app.dependency_overrides[get_artifact_repo] = override_get_artifact_repo
    app.dependency_overrides[get_event_repo] = override_get_event_repo
    app.dependency_overrides[get_object_store] = override_get_object_store
    app.dependency_overrides[get_principal] = override_get_principal

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_get_case(client):
    # Create case
    res1 = client.post("/v1/cases", json={"case_id": "TEST-CASE-API"})
    assert res1.status_code == 200
    data = res1.json()
    assert data["case_id"] == "TEST-CASE-API"
    assert data["status"] == "created"

    # Get case
    res2 = client.get("/v1/cases/TEST-CASE-API")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["case_id"] == "TEST-CASE-API"
    assert data2["status"] == "created"

    # List events
    res3 = client.get("/v1/events?case_id=TEST-CASE-API")
    assert res3.status_code == 200
    events = res3.json()["events"]
    assert len(events) >= 1
    assert events[0]["event_type"] == "case.created"


def test_ingest_case(client):
    client.post("/v1/cases", json={"case_id": "INGEST-TEST"})
    res = client.post("/v1/cases/INGEST-TEST/ingest", json={"use_fixture": "case_0001"})
    
    # In sqlite in-memory, we mock the fixture. But wait, generate_case_0001 returns hardcoded numpy arrays.
    # It should pass Data Guard
    assert res.status_code == 200
    data = res.json()
    assert data["guard_verdict"] == "accepted"
