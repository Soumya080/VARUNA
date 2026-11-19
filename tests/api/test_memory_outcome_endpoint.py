"""GET /v1/cases/{case_id}/memory-outcome — Phase 6B's Verification Ledger
5th axis (docs/product/HONESTY_LEDGER.md #19).
"""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_recorded_case_reports_its_own_outcome():
    client.get("/v1/replay/CASE-VALID")
    r = client.get("/v1/cases/REPLAY-CASE-VALID/memory-outcome")
    assert r.status_code == 200
    body = r.json()
    assert body["case_id"] == "REPLAY-CASE-VALID"
    assert body["recorded"] is True
    assert body["outcome"]


def test_unknown_case_reports_honestly_not_recorded():
    r = client.get("/v1/cases/NO-SUCH-CASE-EVER/memory-outcome")
    assert r.status_code == 200
    body = r.json()
    assert body["recorded"] is False
    assert body["outcome"] is None
