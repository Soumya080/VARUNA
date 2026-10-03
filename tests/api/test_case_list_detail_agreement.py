"""Parametrized contract: every case `GET /v1/cases` lists must agree with
what its own per-case routes actually serve. This is the general form of
the B1 regression lock in `test_demo_clickpath.py` — that file guards the
demo click path specifically; this one is the reusable contract for any
future case-scoped route.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _warmed_case_rows() -> list[dict]:
    fixtures = client.get("/v1/replay/fixtures").json().get("fixtures", [])
    for name in fixtures:
        client.get(f"/v1/replay/{name}")
    return client.get("/v1/cases").json()["items"]


CASE_ROWS = _warmed_case_rows()


@pytest.mark.parametrize("row", CASE_ROWS, ids=lambda r: r["case_id"])
def test_case_detail_agrees_with_list_row(row):
    cid = row["case_id"]
    detail = client.get(f"/v1/cases/{cid}")
    assert detail.status_code == 200, f"{cid} listed but GET /v1/cases/{{id}} -> {detail.status_code}"
    assert detail.json()["status"] == row["status"]


@pytest.mark.parametrize("row", CASE_ROWS, ids=lambda r: r["case_id"])
def test_operator_view_agrees_with_advertised_flag(row):
    cid = row["case_id"]
    resp = client.get(f"/v1/cases/{cid}/operator-view")
    actual = resp.status_code == 200
    assert actual == row["has_operator_view"], (
        f"{cid}: list advertised has_operator_view={row['has_operator_view']} "
        f"but operator-view returned {resp.status_code}"
    )
