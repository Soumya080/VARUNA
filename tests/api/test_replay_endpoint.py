"""
VARUNA GRID — GET /v1/replay/{fixture_name} tests (STEP 4, ADR-0014).
"""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_list_fixtures():
    r = client.get("/v1/replay/fixtures")
    assert r.status_code == 200
    fixtures = r.json()["fixtures"]
    assert "CASE-VALID" in fixtures
    assert "CASE-OOD" in fixtures


def test_unknown_fixture_is_404():
    r = client.get("/v1/replay/NOT-A-REAL-FIXTURE")
    assert r.status_code == 404


def test_case_valid_returns_populated_unified_operator_case():
    r = client.get("/v1/replay/CASE-VALID")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "v1"
    assert body["system_status"]["engine_mode"] == "replay"
    assert body["detection"]["status"] == "produced"
    assert body["detection"]["evidence_mode"] == "real"
    assert body["intelligence"]["status"] == "produced"
    assert body["intelligence"]["hypotheses"] is not None
    assert body["intelligence"]["decision_trace"] is not None


def test_case_ood_never_reaches_a_decision():
    r = client.get("/v1/replay/CASE-OOD")
    assert r.status_code == 200
    body = r.json()
    assert body["intelligence"]["decision_trace"]["terminal_action"] != "proceed_to_decision"


def test_case_simulated_never_reports_real_evidence():
    r = client.get("/v1/replay/CASE-SIMULATED")
    assert r.status_code == 200
    body = r.json()
    for section in ("detection", "origin", "attribution", "forecast"):
        mode = body[section].get("evidence_mode")
        if mode is not None:
            assert mode != "real"


def test_repeated_requests_stay_scientifically_deterministic():
    """This route calls run_replay_case(..., force=True) precisely so that
    repeated requests each recompute intelligence rather than hitting
    GoldenCaseWorkflow's idempotency cache (see the regression test below
    for the bug this fixes). `force=True` means `provenance.artifact_ids`
    (a freshly-registered PRAMAN artifact each call) and `run_id`
    (wall-clock+random) legitimately DIFFER between calls — what must stay
    identical is every actual scientific/evidentiary value, matching the
    convention already established in
    tests/integration/test_product_case_composition.py."""
    r1 = client.get("/v1/replay/CASE-VALID").json()
    r2 = client.get("/v1/replay/CASE-VALID").json()

    assert r1["system_status"]["case_status"] == r2["system_status"]["case_status"]
    assert r1["system_status"]["engine_mode"] == r2["system_status"]["engine_mode"]
    assert r1["detection"]["value"]["classification"] == r2["detection"]["value"]["classification"]
    assert r1["attribution"]["value"]["top_posterior"] == r2["attribution"]["value"]["top_posterior"]
    assert r1["validity"]["value"]["state"] == r2["validity"]["value"]["state"]
    assert r1["recommendation"] == r2["recommendation"]
    top1 = max(r1["intelligence"]["hypotheses"]["hypotheses"], key=lambda h: h["posterior"])
    top2 = max(r2["intelligence"]["hypotheses"]["hypotheses"], key=lambda h: h["posterior"])
    assert top1["source_class"] == top2["source_class"]
    assert top1["posterior"] == top2["posterior"]


def test_intelligence_stays_populated_across_repeated_requests():
    """Regression test for the bug found by this session's runtime
    diagnostic (docs/product/FRONTEND_RUNTIME_DIAGNOSTIC.md): before the
    force=True fix, GoldenCaseWorkflow's idempotency cache made every
    request AFTER the first silently report intelligence.status =
    NOT_YET_PRODUCED, because a cached CaseResult carries no re-runnable
    PipelineRun. Every call, not just the first, must return real
    hypotheses/decision_trace/uncertainty."""
    for _ in range(3):
        body = client.get("/v1/replay/CASE-VALID").json()
        assert body["intelligence"]["status"] == "produced"
        assert body["intelligence"]["hypotheses"] is not None
        assert body["intelligence"]["decision_trace"] is not None
        assert body["intelligence"]["uncertainty"] is not None
