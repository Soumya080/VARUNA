"""
VARUNA GRID — API Tests for Cases Router.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)

def test_create_case():
    response = client.post("/v1/cases", json={"case_id": "TEST-123"})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert data["status"] == "created"

def test_get_case():
    # Assuming TEST-123 was created in the previous test
    # Wait, the state is persisted in memory between tests because dependencies use the global mock!
    response = client.get("/v1/cases/TEST-123")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert data["status"] == "created"
    assert data["scientific_status"] == "EXPERIMENTAL / UNVALIDATED"

def test_ingest_case():
    response = client.post("/v1/cases/TEST-123/ingest", json={"use_fixture": "case_0001"})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert "guard_verdict" in data
    assert data["status"] == "ingesting"

def test_reconstruct_case():
    response = client.post("/v1/cases/TEST-123/reconstruct", json={"seed": 42})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    
def test_attribute_case():
    response = client.post("/v1/cases/TEST-123/attribute", json={"latent_prior": 0.5})
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"

def test_get_phi_and_attribution():
    response = client.get("/v1/cases/TEST-123/phi")
    assert response.status_code == 200
    data = response.json()
    assert "phi_id" in data
    
    response = client.get("/v1/cases/TEST-123/attribution")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "TEST-123"
    assert data["scientific_status"] == "EXPERIMENTAL / UNVALIDATED"
