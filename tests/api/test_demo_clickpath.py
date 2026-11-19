"""The demo click-path regression lock.

A judge's first action is to open the case list and click a case. Before this
test existed, `GET /v1/cases` advertised `has_operator_view: true` for cases
whose per-case routes returned 404 — the flag was in fact *inverted*, because
the list route consults three case stores while every per-case route consults
only one, and `has_operator_view` was computed from a cache keyed by FIXTURE
NAME while the rows are keyed by CASE ID.

This test encodes the invariant that was missing: **anything the list route
advertises, the per-case routes must actually serve.** It is deliberately
written against the live API surface rather than the internals, because that
is the contract a client depends on.
"""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _listed_cases() -> list[dict]:
    r = client.get("/v1/cases")
    assert r.status_code == 200, f"case list itself failed: {r.status_code}"
    return r.json()["items"]


def _warm_replay_cache() -> None:
    """Replay cases only exist once their fixture has been composed at least
    once. A judge reaches them via the cockpit, which does exactly this — so
    the test reproduces the real click path rather than a colder one."""
    fixtures = client.get("/v1/replay/fixtures").json()
    for name in fixtures.get("fixtures", []):
        client.get(f"/v1/replay/{name}")


def test_case_list_is_not_empty():
    _warm_replay_cache()
    assert len(_listed_cases()) > 0, "no cases to click — the demo has nothing to show"


def test_every_listed_case_can_be_opened():
    """B1: `GET /v1/cases/{id}` must 200 for every case the list returns."""
    _warm_replay_cache()
    failures = []
    for row in _listed_cases():
        cid = row["case_id"]
        code = client.get(f"/v1/cases/{cid}").status_code
        if code != 200:
            failures.append(f"{cid} -> {code}")
    assert not failures, (
        "cases listed by /v1/cases but not retrievable by /v1/cases/{id}: "
        + ", ".join(failures)
    )


def test_has_operator_view_flag_matches_reality():
    """B1's sharpest edge: the advertised flag must agree with the route.

    A `true` that 404s is worse than a `false` — it sends a client down a path
    the server cannot serve.
    """
    _warm_replay_cache()
    disagreements = []
    for row in _listed_cases():
        cid = row["case_id"]
        advertised = bool(row.get("has_operator_view"))
        actual = client.get(f"/v1/cases/{cid}/operator-view").status_code == 200
        if advertised != actual:
            disagreements.append(
                f"{cid}: has_operator_view={advertised} but operator-view "
                f"{'succeeds' if actual else '404s'}"
            )
    assert not disagreements, "\n".join(disagreements)
