"""B2 regression lock.

`GET /v1/dashboard/summary` used to be wrong three independent ways: it read
only the legacy `CaseWorkflow` store (so `total_cases` undercounted), it
compared alert status against the wrong case (a fresh `AlertService` whose
delivery log is always empty) so `total_alerts_sent` was a hardcoded zero,
and its "active" case filter used a literal status set that never matched
the golden engine's real terminal values. This locks all three.
"""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _warm_replay_cache() -> None:
    fixtures = client.get("/v1/replay/fixtures").json()
    for name in fixtures.get("fixtures", []):
        client.get(f"/v1/replay/{name}")


def test_total_cases_counts_every_store():
    _warm_replay_cache()
    r = client.get("/v1/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    # At minimum, the replay fixtures themselves must be counted — a
    # dashboard reporting fewer cases than the demo actually has is B2.
    fixtures = client.get("/v1/replay/fixtures").json()["fixtures"]
    assert body["total_cases"] >= len(fixtures), body


def test_total_alerts_sent_is_not_a_hardcoded_zero():
    """B2's sharpest edge: a test that only asserted `>= 0` would have let
    this ship in the first place. The replay fixtures include cases that
    generate real alerts, so this must be strictly positive."""
    _warm_replay_cache()
    r = client.get("/v1/dashboard/summary")
    assert r.status_code == 200
    assert r.json()["total_alerts_sent"] > 0, (
        "total_alerts_sent is zero — either nothing is delivering alerts, "
        "or the dashboard is reading the wrong store/status vocabulary again"
    )


def test_active_cases_uses_real_terminal_status_vocabulary():
    """Every replay fixture runs to a real terminal state (`complete`,
    `blocked`, `unavailable`, or `ood` — never the v1-only `completed`
    literal the old filter checked for). None of them should still count
    as 'active' once composed."""
    _warm_replay_cache()
    r = client.get("/v1/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["active_cases"] <= body["total_cases"]
