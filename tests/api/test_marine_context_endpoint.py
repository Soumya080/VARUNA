"""Phase 9 — GET /v1/dashboard/marine-context."""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_returns_all_three_sources_honestly():
    r = client.get("/v1/dashboard/marine-context")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"era5", "cmems", "ais"}
    for source_id, entry in body.items():
        assert "tier" in entry
        assert "label" in entry
        assert "live" not in entry["label"].lower()


def test_no_authentication_required():
    """A read-only diagnostic, not a mutation — should not require login."""
    r = client.get("/v1/dashboard/marine-context")
    assert r.status_code == 200
