"""
Phase 3 — real email + SMS delivery.

The HTTP layer is mocked throughout: a test suite must never hit a real SMS
gateway (it costs money and messages real handsets). What is proven here is
that the clients build the right request, parse the provider's own success
flag rather than trusting the status code, and — above all — that an
unconfigured integration reports NOT_CONFIGURED and never SUCCESS.
"""
import httpx
import pytest

from varuna_alerts.channel_orchestrator import (
    ChannelMode, ChannelOrchestrator, DeliveryStatus, contact_for, recipients_config,
)
from varuna_alerts.channels.sms_gateway import send_sms, sms_provider_status
from varuna_alerts.templates import render_html, render_sms, render_subject, render_text


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("VARUNA_SMTP_HOST", "VARUNA_SMTP_USER", "VARUNA_SMTP_PASSWORD",
                "VARUNA_ALERT_TO", "VARUNA_SMS_PROVIDER", "VARUNA_SMS_API_KEY",
                "VARUNA_SMS_SENDER_ID"):
        monkeypatch.delenv(var, raising=False)
    import varuna_alerts.channel_orchestrator as co
    monkeypatch.setattr(co, "_RECIPIENTS_CACHE", None)


REAL_ALERT = {
    "alert_id": "ALT-1", "case_id": "CASE-9", "severity": "critical",
    "event_type": "landfall.predicted", "material_dimension": "landfall.prediction",
    "reason": "forecast predicts landfall at Replay coastal segment",
    "severity_basis": "a landfall is predicted while the validity gate blocks action",
    "engine_mode": "real", "is_simulated": False,
    "created_at": "2026-09-03T10:00:00Z", "evidence_refs": ["forecast-CASE-9"],
    "previous_value": 0, "current_value": 1, "routing": {},
}
REPLAY_ALERT = {**REAL_ALERT, "engine_mode": "replay", "is_simulated": True}


# ------------------------------------------------------------- templates

def test_real_and_replay_are_unmistakable_in_every_rendering():
    """The one thing that must never be ambiguous at 02:00."""
    assert "REAL OPERATIONAL ALERT" in render_text(REAL_ALERT)
    assert "[DRILL]" not in render_subject(REAL_ALERT)

    assert "NOT A REAL OPERATIONAL EVENT" in render_text(REPLAY_ALERT)
    # Phase 2a: subject/SMS now lead with the message-precedence word
    # (FLASH/IMMEDIATE/PRIORITY/ROUTINE), so [DRILL] is no longer the first
    # token — it must still appear, unambiguously, in both.
    assert "[DRILL]" in render_subject(REPLAY_ALERT)
    assert "[DRILL]" in render_sms(REPLAY_ALERT)


def test_templates_are_not_the_old_debug_stub():
    """The previous implementation returned
    f'Alert {id} with context {dict}' — which would have been texted verbatim."""
    for rendered in (render_text(REAL_ALERT), render_sms(REAL_ALERT)):
        assert "with context {" not in rendered


def test_text_carries_the_operator_decision_context():
    out = render_text(REAL_ALERT)
    for expected in ("CASE-9", "CRITICAL", "landfall.prediction",
                     "Why this severity", "forecast-CASE-9"):
        assert expected in out


def test_sms_is_bounded_and_cut_on_a_word_boundary():
    long_alert = {**REAL_ALERT, "reason": "word " * 400}
    out = render_sms(long_alert)
    assert len(out) <= 300
    assert out.endswith("…")
    assert not out[:-1].endswith(" ")


def test_html_escapes_injected_content():
    nasty = {**REAL_ALERT, "reason": "<script>alert(1)</script>"}
    out = render_html(nasty)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


# --------------------------------------------------------- configuration

def test_unconfigured_sms_is_not_configured_never_success():
    st = sms_provider_status()
    assert st["mode"] == ChannelMode.NOT_CONFIGURED.value
    assert "VARUNA_SMS_PROVIDER" in st["reason"]


def test_unknown_provider_is_named_not_silently_accepted(monkeypatch):
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "some-gateway")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")
    st = sms_provider_status()
    assert st["mode"] == ChannelMode.NOT_CONFIGURED.value
    assert "some-gateway" in st["reason"]


def test_msg91_requires_a_sender_id(monkeypatch):
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "msg91")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")
    assert sms_provider_status()["mode"] == ChannelMode.NOT_CONFIGURED.value
    monkeypatch.setenv("VARUNA_SMS_SENDER_ID", "VARUNA")
    assert sms_provider_status()["mode"] == ChannelMode.REAL.value


def test_configured_provider_but_no_phone_names_the_role(monkeypatch):
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "fast2sms")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")
    d = send_sms(alert_id="A", recipient_role="state_pcb", phone=None, body="x")
    assert d.status is DeliveryStatus.NOT_CONFIGURED
    assert "state_pcb" in d.detail


# ------------------------------------------------------- real send paths

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fast2sms_success_is_parsed_from_the_body_not_the_status(monkeypatch):
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "fast2sms")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"return": True, "message": ["queued"]})

    d = send_sms(alert_id="A", recipient_role="duty_officer",
                 phone="+919876543210", body="hello", client=_client(handler))
    assert d.status is DeliveryStatus.SENT
    assert d.mode is ChannelMode.REAL
    assert "fast2sms.com" in seen["url"]
    assert seen["auth"] == "k"


def test_gateway_200_with_failure_body_is_FAILED_not_sent(monkeypatch):
    """The trap this guards: Indian gateways return HTTP 200 while rejecting
    the message downstream."""
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "fast2sms")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")

    def handler(request):
        return httpx.Response(200, json={"return": False, "message": "Invalid Sender ID"})

    d = send_sms(alert_id="A", recipient_role="duty_officer",
                 phone="+919876543210", body="hi", client=_client(handler))
    assert d.status is DeliveryStatus.FAILED
    assert "Invalid Sender ID" in (d.error or "")


def test_msg91_error_body_is_FAILED(monkeypatch):
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "msg91")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")
    monkeypatch.setenv("VARUNA_SMS_SENDER_ID", "VARUNA")

    def handler(request):
        return httpx.Response(200, text='{"type":"error","message":"authkey invalid"}')

    d = send_sms(alert_id="A", recipient_role="duty_officer",
                 phone="+919876543210", body="hi", client=_client(handler))
    assert d.status is DeliveryStatus.FAILED


def test_successful_send_claims_SENT_never_DELIVERED(monkeypatch):
    """We receive no delivery callback, so handset delivery is unknowable."""
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "fast2sms")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")

    def handler(request):
        return httpx.Response(200, json={"return": True})

    d = send_sms(alert_id="A", recipient_role="duty_officer",
                 phone="+919876543210", body="hi", client=_client(handler))
    assert d.status is DeliveryStatus.SENT
    assert d.status is not DeliveryStatus.DELIVERED
    assert "not proof of handset delivery" in d.detail


def test_network_failure_is_FAILED_with_the_real_error(monkeypatch):
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "fast2sms")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")

    def handler(request):
        raise httpx.ConnectError("no route to host")

    d = send_sms(alert_id="A", recipient_role="duty_officer",
                 phone="+919876543210", body="hi", client=_client(handler))
    assert d.status is DeliveryStatus.FAILED
    assert "ConnectError" in (d.error or "")


# ------------------------------------------------------------- registry

def test_recipient_registry_loads_and_external_roles_exist():
    cfg = recipients_config()
    assert "duty_officer" in cfg
    for external in ("enforcement", "dg_shipping", "state_pcb"):
        assert external in cfg, "external stakeholder roles must be addressable"


def test_missing_contact_is_not_an_error():
    """A role with no contact is a normal state, reported honestly."""
    assert contact_for("duty_officer").get("email") is None
    assert contact_for("no_such_role") == {}


# -------------------------------------------------------- channel report

def test_channel_report_is_honest_when_nothing_is_configured():
    report = ChannelOrchestrator.channel_report()
    assert report["dashboard"] == "REAL"
    assert report["browser_push"] == "SIMULATED"
    assert report["email"] == "NOT_CONFIGURED"
    assert report["sms"] == "NOT_CONFIGURED"
    assert "SUCCESS" not in report.values()


def test_channel_report_flips_to_real_when_configured(monkeypatch):
    monkeypatch.setenv("VARUNA_SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("VARUNA_SMS_PROVIDER", "msg91")
    monkeypatch.setenv("VARUNA_SMS_API_KEY", "k")
    monkeypatch.setenv("VARUNA_SMS_SENDER_ID", "VARUNA")
    report = ChannelOrchestrator.channel_report()
    assert report["email"] == "REAL"
    assert report["sms"] == "REAL"


def test_whatsapp_and_zoho_are_not_offered_as_channels():
    """Both were adapter-shape-only stubs and were removed outright (Phase 0a) —
    not just excluded from the default set."""
    report = ChannelOrchestrator.channel_report()
    assert "zoho_cliq" not in report
    assert "whatsapp" not in report
    assert "zoho_cliq" not in ChannelOrchestrator().channels
    assert "whatsapp" not in ChannelOrchestrator().channels
    from varuna_alerts.channel_orchestrator import ADAPTERS
    assert set(ADAPTERS) == {"dashboard", "browser_push", "email", "sms"}
