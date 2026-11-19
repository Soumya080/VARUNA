"""GET /v1/chhaya/tiles and /v1/chhaya/investigate/{tile_id} — the real CHHAYA
v2 pipeline (packages/varuna_chhaya/v2) wired over real MC20 Sentinel-1 tiles.

Skipped automatically when the MC20 gold event data isn't present on disk
(e.g. a CI checkout without the large data fixtures) — this test verifies
real behavior, it does not fabricate data to run against.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _tiles():
    r = client.get("/v1/chhaya/tiles")
    assert r.status_code == 200
    return r.json()


def test_tiles_endpoint_reports_availability_honestly():
    d = _tiles()
    assert "available" in d
    if not d["available"]:
        assert d["reason"], "an unavailable response must say why"


@pytest.fixture
def first_tile_id():
    d = _tiles()
    if not d.get("available") or not d.get("tiles"):
        pytest.skip("MC20 gold event SAR tiles not present on disk in this environment")
    return d["tiles"][0]["tile_id"]


def test_investigate_response_shape(first_tile_id):
    r = client.get(f"/v1/chhaya/investigate/{first_tile_id}")
    assert r.status_code == 200
    body = r.json()
    for key in ("outcome", "outcome_reason", "detector_source", "detector_mode",
                "detector_available", "candidates", "_input"):
        assert key in body

    inp = body["_input"]
    for key in ("tile_id", "tile_shape", "n_ais_positions_in_tile",
                "ais_positions", "corridor_recurrence", "detector_note"):
        assert key in inp, f"missing new/existing field: {key}"


def test_ais_positions_count_matches_declared_count(first_tile_id):
    r = client.get(f"/v1/chhaya/investigate/{first_tile_id}")
    inp = r.json()["_input"]
    assert len(inp["ais_positions"]) == inp["n_ais_positions_in_tile"]
    for p in inp["ais_positions"]:
        assert "lon" in p and "lat" in p


def test_corridor_recurrence_is_a_real_nonnegative_count(first_tile_id):
    r = client.get(f"/v1/chhaya/investigate/{first_tile_id}")
    rec = r.json()["_input"]["corridor_recurrence"]
    assert rec["radius_km"] == 50.0
    assert isinstance(rec["count"], int)
    assert rec["count"] >= 0


def test_unknown_tile_is_404():
    r = client.get("/v1/chhaya/investigate/NOT-A-REAL-TILE-ID")
    assert r.status_code == 404
