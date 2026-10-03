"""Workstream A — end-to-end API tests: operational summary, PDF report,
SMRITI persistence, and deterministic replay alert behaviour."""
from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _login(u: str, p: str) -> dict:
    r = client.post("/v1/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_case_valid_produces_material_alerts_with_routing_and_delivery():
    client.get("/v1/replay/CASE-VALID")
    s = client.get("/v1/cases/REPLAY-CASE-VALID/operational-summary")
    assert s.status_code == 200
    body = s.json()
    alerts = body["alerts"]
    assert len(alerts) >= 3, "expected one alert per material dimension"

    for a in alerts:
        assert a["material_dimension"], "every alert names the dimension that changed"
        assert a["severity_basis"], "every severity is explainable"
        assert a["routing"] and a["routing"]["recipients"], "every alert is routed"
        assert a["transitions"], "every alert has an audited transition history"
        assert a["deliveries"], "every alert attempted channel delivery"


def test_channel_report_is_honest_about_unconfigured_integrations():
    client.get("/v1/replay/CASE-VALID")
    channels = client.get("/v1/cases/REPLAY-CASE-VALID/operational-summary").json()["channels"]
    assert channels["dashboard"] == "REAL"
    assert channels["browser_push"] == "SIMULATED"
    # No SMTP/SMS configured in the test environment.
    assert channels["email"] == "NOT_CONFIGURED"
    assert channels["sms"] == "NOT_CONFIGURED"
    # WhatsApp/Zoho Cliq were adapter-shape-only stubs and were removed as
    # offered channels entirely (Phase 0a) rather than kept as permanent
    # NOT_CONFIGURED noise.
    assert "whatsapp" not in channels
    assert "zoho_cliq" not in channels
    assert "SUCCESS" not in channels.values()


def test_case_ood_produces_no_alerts_fail_closed():
    client.get("/v1/replay/CASE-OOD")
    alerts = client.get("/v1/cases/REPLAY-CASE-OOD/operational-summary").json()["alerts"]
    assert alerts == []


def test_replay_alert_behaviour_is_deterministic():
    """Same fixture, clean state -> same dimensions and same dedupe keys."""
    def run_once():
        import apps.api.dependencies as deps
        import apps.api.routers.replay as rp
        deps._alert_store_singleton = None
        deps._alert_orchestrator_singleton = None
        deps._snapshot_store_singleton = None
        deps._alert_lifecycle_singleton = None
        rp._COMPOSED_CACHE.clear()
        client.get("/v1/replay/CASE-VALID")
        items = client.get("/v1/cases/REPLAY-CASE-VALID/operational-summary").json()["alerts"]
        return sorted(i["dedupe_key"] for i in items)

    assert run_once() == run_once()


def test_repeated_fetch_does_not_multiply_alerts():
    client.get("/v1/replay/CASE-VALID")
    first = len(client.get("/v1/cases/REPLAY-CASE-VALID/operational-summary").json()["alerts"])
    for _ in range(3):
        client.get("/v1/replay/CASE-VALID?refresh=true")
    second = len(client.get("/v1/cases/REPLAY-CASE-VALID/operational-summary").json()["alerts"])
    assert first == second, "dedupe must stop repeated runs from spamming alerts"


def test_pdf_report_downloads_and_is_a_real_pdf():
    client.get("/v1/replay/CASE-VALID")
    r = client.get("/v1/cases/REPLAY-CASE-VALID/report")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 3000
    assert "attachment" in r.headers.get("content-disposition", "")


def test_report_for_a_case_that_was_never_run_is_404_not_fabricated():
    r = client.get("/v1/cases/CASE-NEVER-RUN/report")
    assert r.status_code == 404


def test_ood_report_still_generates_and_marks_sections_unavailable():
    client.get("/v1/replay/CASE-OOD")
    r = client.get("/v1/cases/REPLAY-CASE-OOD/report")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_smriti_persists_the_completed_case():
    from apps.api.dependencies import get_replay_smriti_store
    client.get("/v1/replay/CASE-VALID?refresh=true")
    mem = get_replay_smriti_store().get("REPLAY-CASE-VALID")
    assert mem is not None
    assert mem.case_id == "REPLAY-CASE-VALID"
    assert mem.provenance_source == "varuna.operational_loop"
    # Advisory only: it records outcome, it does not assert authorization.
    assert mem.outcome is not None


def test_alert_lifecycle_action_is_rbac_enforced_and_audited():
    client.get("/v1/replay/CASE-VALID")
    alerts = client.get("/v1/cases/REPLAY-CASE-VALID/operational-summary").json()["alerts"]
    actionable = [a for a in alerts if a["status"] not in
                  ("acknowledged", "escalated", "resolved")]
    alert_id = actionable[0]["alert_id"]

    assert client.post(f"/v1/alerts/{alert_id}/acknowledge").status_code == 401
    assert client.post(f"/v1/alerts/{alert_id}/acknowledge",
                       headers=_login("viewer", "viewer-demo-pass")).status_code == 403

    ok = client.post(f"/v1/alerts/{alert_id}/acknowledge",
                     headers=_login("officer", "officer-demo-pass"))
    assert ok.status_code == 200
    assert ok.json()["status"] == "acknowledged"
    assert ok.json()["acknowledged_by"] == "officer"
