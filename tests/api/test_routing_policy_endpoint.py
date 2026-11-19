"""GET /v1/alerts/routing-policy — the static alert-routing decision table
(Phase 0c/2b). Public/read-only (no alert data, no credentials involved)."""
from fastapi.testclient import TestClient

from apps.api.main import app
from varuna_alerts.material_change import MaterialDimension

client = TestClient(app)


def test_enumerates_all_dimensions_and_urgency_severities():
    r = client.get("/v1/alerts/routing-policy")
    assert r.status_code == 200
    items = r.json()["items"]
    dims = {i["dimension"] for i in items}
    assert dims == {d.value for d in MaterialDimension}
    severities = {i["severity"] for i in items}
    assert severities == {"low", "medium", "high", "critical"}
    assert len(items) == len(MaterialDimension) * 4


def test_unmatched_dimension_falls_back_to_duty_officer_only():
    r = client.get("/v1/alerts/routing-policy")
    items = r.json()["items"]
    row = next(i for i in items if i["dimension"] == "detection.presence" and i["severity"] == "low")
    assert [rec["role"] for rec in row["recipients"]] == ["duty_officer"]
    assert "new-detection-to-duty-officer" in row["matched_rule"]


def test_critical_always_escalates_to_supervisor():
    r = client.get("/v1/alerts/routing-policy")
    items = r.json()["items"]
    for row in items:
        if row["severity"] == "critical":
            roles = [rec["role"] for rec in row["recipients"]]
            assert "supervisor" in roles, f"{row['dimension']} at critical must reach supervisor"


def test_landfall_reaches_external_authorities():
    r = client.get("/v1/alerts/routing-policy")
    items = r.json()["items"]
    row = next(i for i in items if i["dimension"] == "landfall.prediction" and i["severity"] == "low")
    roles = {rec["role"] for rec in row["recipients"]}
    assert "state_pcb" in roles
    assert "dg_shipping" in roles


def test_titles_resolve_from_recipients_yaml_not_a_second_hardcoded_map():
    r = client.get("/v1/alerts/routing-policy")
    items = r.json()["items"]
    row = next(i for i in items if i["dimension"] == "detection.presence" and i["severity"] == "low")
    duty = next(rec for rec in row["recipients"] if rec["role"] == "duty_officer")
    assert duty["title"] == "Duty Officer, Coastal Watch"


def test_external_roles_have_no_rbac_role():
    r = client.get("/v1/alerts/routing-policy")
    items = r.json()["items"]
    row = next(i for i in items if i["dimension"] == "landfall.prediction" and i["severity"] == "low")
    for rec in row["recipients"]:
        if rec["role"] in ("state_pcb", "dg_shipping", "enforcement"):
            assert rec["rbac_role"] is None


def test_no_authentication_required():
    """This is a static policy reference, not an alert or a send — must not
    require a login, unlike test-notification."""
    r = client.get("/v1/alerts/routing-policy")
    assert r.status_code == 200
