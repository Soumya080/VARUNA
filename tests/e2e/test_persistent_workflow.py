"""
VARUNA GRID — E2E Persistent Workflow Test.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.security import get_principal
from varuna_infra.authorization import Principal

pytestmark = [pytest.mark.e2e]

client = TestClient(app)


@pytest.fixture(autouse=True)
def _authenticated_principal():
    """Case-mutation endpoints require an authenticated Principal as of
    Phase 5 (VARUNA_PRODUCT_READY hardening); this test exercises the
    workflow under a role holding every permission it needs, not the
    identity-resolution logic itself (covered by
    tests/unit/test_api_security.py). Scoped to this module and torn down
    after each test so it cannot leak into other test files sharing the same
    `app` singleton."""
    app.dependency_overrides[get_principal] = lambda: Principal(
        principal_id="test-duty-officer", role="duty_officer")
    yield
    app.dependency_overrides.pop(get_principal, None)


def test_full_workflow_end_to_end():
    # 1. Create Case
    case_id = "CASE-E2E-001"
    resp = client.post("/v1/cases", json={"case_id": case_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"
    
    # 2. Ingest
    resp = client.post(f"/v1/cases/{case_id}/ingest", json={"use_fixture": "case_0001"})
    assert resp.status_code == 200
    # "guarding" is the only correct resting status on the accept path — see
    # tests/api/test_cases.py::test_ingest_case for why.
    assert resp.json()["status"] == "guarding"
    
    # 3. Reconstruct
    resp = client.post(f"/v1/cases/{case_id}/reconstruct", json={"seed": 42})
    assert resp.status_code == 200
    
    # 4. Attribute
    resp = client.post(f"/v1/cases/{case_id}/attribute", json={"latent_prior": 0.5})
    assert resp.status_code == 200
    
    # 5. Fetch Case State
    resp = client.get(f"/v1/cases/{case_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["n_artifacts"] >= 3
    assert data["n_events"] >= 5
    assert data["scientific_status"] == "EXPERIMENTAL / UNVALIDATED"
    
    # 6. Fetch Attribution
    resp = client.get(f"/v1/cases/{case_id}/attribution")
    assert resp.status_code == 200
    attr_data = resp.json()
    assert attr_data["decision_state"] == "strong_lead"
    assert "candidates" in attr_data
    assert len(attr_data["candidates"]) > 0
