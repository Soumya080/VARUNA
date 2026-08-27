"""
VARUNA GRID — E2E Persistent Workflow Test.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

pytestmark = [pytest.mark.e2e]

client = TestClient(app)

def test_full_workflow_end_to_end():
    # 1. Create Case
    case_id = "CASE-E2E-001"
    resp = client.post("/v1/cases", json={"case_id": case_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"
    
    # 2. Ingest
    resp = client.post(f"/v1/cases/{case_id}/ingest", json={"use_fixture": "case_0001"})
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ingesting", "guarding")
    
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
