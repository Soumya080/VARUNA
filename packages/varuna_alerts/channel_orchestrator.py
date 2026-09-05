"""
VARUNA — Channel Orchestrator (Workstream A, Phase 7).

The hard rule this module exists to enforce: **an unconfigured integration
reports NOT_CONFIGURED, never SUCCESS.** Nothing here invents a provider
response, a message id, or a delivery confirmation.

Configuration is read from the environment at send time. No credentials are
stored in code, and no default credentials exist — absence of configuration
is the normal state and is reported honestly rather than treated as an error.

Channel reality today:
  dashboard        REAL       — an in-app record the cockpit genuinely reads
  browser_push     SIMULATED  — recorded server-side; real Web Push needs a
                                VAPID keypair + a service worker, neither of
                                which exists in this repo
  email            REAL when VARUNA_SMTP_HOST is set, else NOT_CONFIGURED
  sms              REAL when VARUNA_SMS_PROVIDER + key are set, else NOT_CONFIGURED

WhatsApp and Zoho Cliq are deliberately NOT offered as channels. Both were
adapter-shape-only stubs (no HTTP client, no credentials, no delivery path)
and offering them alongside four genuinely real/simulated channels made the
whole channel list read as less trustworthy than it is. If a real WhatsApp
Business API or Zoho Cliq integration is ever built, add it back here with a
real adapter function — never re-add a `_unimplemented()` placeholder.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ChannelMode(StrEnum):
    """Mirrors the REAL / SIMULATED / NOT_CONFIGURED vocabulary used
    everywhere else in VARUNA, applied to delivery rather than evidence."""

    REAL = "REAL"
    SIMULATED = "SIMULATED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class NotificationDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str = Field(default_factory=lambda: f"dlv-{uuid.uuid4().hex[:10]}")
    alert_id: str
    channel: str
    recipient_role: str
    status: DeliveryStatus
    mode: ChannelMode
    attempt: int = 1
    provider: str | None = None
    error: str | None = None
    detail: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# Recipient registry - role -> {email, phone}. Routing decides WHICH roles;
# this is the only place that knows how to reach them. A role with no contact
# is reported NOT_CONFIGURED by name, never silently dropped.
# --------------------------------------------------------------------------

_RECIPIENTS_CACHE: dict | None = None


def recipients_config(path=None) -> dict:
    global _RECIPIENTS_CACHE
    if _RECIPIENTS_CACHE is not None and path is None:
        return _RECIPIENTS_CACHE
    from pathlib import Path

    p = Path(path) if path else Path(
        os.environ.get("VARUNA_RECIPIENTS_FILE")
        or Path(__file__).resolve().parents[2] / "configs" / "recipients.yaml"
    )
    data: dict = {}
    if p.exists():
        try:
            import yaml
            loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            data = loaded.get("recipients") or {}
        except Exception:
            data = {}
    if path is None:
        _RECIPIENTS_CACHE = data
    return data


def contact_for(role: str) -> dict:
    return recipients_config().get(role) or {}


# --------------------------------------------------------------------------
# Adapters. Each returns a NotificationDelivery describing what genuinely
# happened. None of them pretends.
# --------------------------------------------------------------------------

def _dashboard(alert_id: str, role: str, subject: str, body: str) -> NotificationDelivery:
    """REAL: the cockpit reads alerts straight from the alert store, so an
    in-app 'delivery' is genuinely complete the moment the record exists."""
    return NotificationDelivery(
        alert_id=alert_id, channel="dashboard", recipient_role=role,
        status=DeliveryStatus.DELIVERED, mode=ChannelMode.REAL,
        provider="varuna.cockpit",
        detail="Alert is readable in the operator cockpit alert surface.",
    )


def _browser_push(alert_id: str, role: str, subject: str, body: str) -> NotificationDelivery:
    return NotificationDelivery(
        alert_id=alert_id, channel="browser_push", recipient_role=role,
        status=DeliveryStatus.SENT, mode=ChannelMode.SIMULATED,
        provider="varuna.local",
        detail=("Recorded server-side only. Real Web Push requires a VAPID keypair and a "
                "registered service worker; neither is configured in this repository, so "
                "no push was actually transmitted."),
    )


def _email(alert_id: str, role: str, subject: str, body: str) -> NotificationDelivery:
    """Real email via Resend, Twilio, or SMTP."""
    provider = os.environ.get("VARUNA_EMAIL_PROVIDER", "").strip().lower()
    host = os.environ.get("VARUNA_SMTP_HOST")
    
    if provider == "resend":
        if not os.environ.get("VARUNA_RESEND_API_KEY"):
            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
                detail="VARUNA_RESEND_API_KEY is not set.",
            )
    elif provider == "twilio":
        if not os.environ.get("VARUNA_TWILIO_EMAIL_KEY"):
            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
                detail="VARUNA_TWILIO_EMAIL_KEY is not set.",
            )
    elif not host:
        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            detail="VARUNA_SMTP_HOST is not set - no SMTP server configured.",
        )

    to_addr = contact_for(role).get("email") or os.environ.get("VARUNA_ALERT_TO")
    if not to_addr:
        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            provider=provider or host,
            detail=("no email configured for role " + repr(role) +
                    " in configs/recipients.yaml and no VARUNA_ALERT_TO fallback."),
        )

    # ── Resend provider ──
    if provider == "resend":
        try:
            import httpx

            api_key = os.environ["VARUNA_RESEND_API_KEY"]
            from_addr = os.environ.get("VARUNA_RESEND_FROM_EMAIL", "onboarding@resend.dev")
            html_body = _HTML_BODIES.get(alert_id) or (
                f'<!doctype html><html><body style="margin:0;background:#eef1f5;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
                f'<div style="max-width:600px;margin:0 auto;background:#ffffff">'
                f'<div style="height:3px;background:linear-gradient(90deg,#e8871a 33%,#ffffff 33% 66%,#1a7f5a 66%)"></div>'
                f'<div style="background:#b3261e;color:#ffffff;padding:8px 20px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:600">'
                f'VARUNA GRID — MARITIME ALERT</div>'
                f'<div style="padding:20px">'
                f'<div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#5b6472">VARUNA GRID · Maritime Surveillance</div>'
                f'<h1 style="margin:6px 0 2px;font-size:20px;color:#12213d">{subject}</h1>'
                f'<p style="margin:0 0 14px;font-size:14px;color:#3b4759">{body}</p>'
                f'<p style="margin:18px 0 0;font-size:12px;color:#5b6472">Acknowledge in the VARUNA cockpit. This message is a notification only.</p>'
                f'</div>'
                f'<div style="padding:10px 20px;background:#12213d;color:#8d9bb2;font-size:11px">Govt. of India · Restricted · For official use only</div>'
                f'</div></body></html>'
            )

            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": from_addr,
                    "to": [to_addr],
                    "subject": subject or "VARUNA Maritime Alert",
                    "html": html_body,
                },
                timeout=15.0,
            )
            resp.raise_for_status()

            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.SENT, mode=ChannelMode.REAL,
                provider="resend",
                detail=("delivered via Resend to " + to_addr + "."),
            )
        except Exception as exc:
            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.FAILED, mode=ChannelMode.REAL, provider="resend",
                error=type(exc).__name__ + ": " + str(exc),
            )

    # ── Twilio provider ──
    if provider == "twilio":
        try:
            import httpx
            
            key = os.environ.get("VARUNA_TWILIO_EMAIL_KEY", "")
            from_addr = os.environ.get("VARUNA_TWILIO_FROM_EMAIL", "varuna@twilio.email")
            html_body = _HTML_BODIES.get(alert_id) or f"<p>{body}</p>"
            
            resp = httpx.post(
                "https://comms.twilio.com/v1/Emails",
                auth=(key.split(":")[0], key.split(":")[1]) if ":" in key else None,
                headers={"Content-Type": "application/json"},
                json={
                    "from": {"address": from_addr, "name": "VARUNA Alerts"},
                    "to": [{"address": to_addr}],
                    "content": {
                        "subject": subject or "VARUNA Maritime Alert",
                        "html": html_body,
                    }
                },
                timeout=15.0
            )
            resp.raise_for_status()
            
            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.SENT, mode=ChannelMode.REAL,
                provider="twilio-email",
                detail=("handed to Twilio for " + to_addr +
                        ". API acceptance is not proof of inbox delivery."),
            )
        except Exception as exc:
            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.FAILED, mode=ChannelMode.REAL, provider="twilio-email",
                error=type(exc).__name__ + ": " + str(exc),
            )

    try:
        import smtplib
        from email.message import EmailMessage

        port = int(os.environ.get("VARUNA_SMTP_PORT", "587"))
        user = os.environ.get("VARUNA_SMTP_USER")
        password = os.environ.get("VARUNA_SMTP_PASSWORD")
        from_addr = os.environ.get("VARUNA_ALERT_FROM") or user or "varuna-alerts@localhost"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.set_content(body)
        html_body = _HTML_BODIES.get(alert_id)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if port in (587, 25) and os.environ.get("VARUNA_SMTP_STARTTLS", "1") != "0":
                try:
                    smtp.starttls()
                    smtp.ehlo()
                except smtplib.SMTPException:
                    pass
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)

        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.SENT, mode=ChannelMode.REAL,
            provider="smtp://" + str(host) + ":" + str(port),
            detail=("handed to SMTP for " + to_addr +
                    ". SMTP acceptance is not proof of inbox delivery."),
        )
    except Exception as exc:
        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.FAILED, mode=ChannelMode.REAL, provider=host,
            error=type(exc).__name__ + ": " + str(exc),
        )


def _sms(alert_id: str, role: str, subject: str, body: str) -> NotificationDelivery:
    """Delegates to the real MSG91 / Fast2SMS client."""
    from varuna_alerts.channels.sms_gateway import send_sms

    return send_sms(
        alert_id=alert_id, recipient_role=role,
        phone=contact_for(role).get("phone"),
        body=_SMS_BODIES.get(alert_id) or body,
    )


ADAPTERS = {
    "dashboard": _dashboard,
    "browser_push": _browser_push,
    "email": _email,
    "sms": _sms,
}

#: Channels attempted for every alert, in priority order. Dashboard first so
#: the operator surface is always populated even when nothing external is
#: configured.
DEFAULT_CHANNELS = ["dashboard", "browser_push", "email", "sms"]

#: Rendered bodies for the alert currently being dispatched. Populated by
#: ChannelOrchestrator.deliver() so the adapters can use the real HTML/SMS
#: templates without changing the adapter signature every call site uses.
_HTML_BODIES: dict[str, str] = {}
_SMS_BODIES: dict[str, str] = {}


class ChannelOrchestrator:
    def __init__(self, channels: list[str] | None = None):
        self.channels = channels or list(DEFAULT_CHANNELS)

    def deliver(self, *, alert_id: str, recipient_roles: list[str], subject: str,
                body: str, alert=None) -> list[NotificationDelivery]:
        """`alert` is optional; when supplied, email and SMS use the real
        rendered templates instead of the bare reason string."""
        if alert is not None:
            try:
                from varuna_alerts.templates import render_html, render_sms, render_text

                _HTML_BODIES[alert_id] = render_html(alert)
                _SMS_BODIES[alert_id] = render_sms(alert)
                body = render_text(alert)
            except Exception:
                pass  # fall back to the plain body; never block delivery

        out: list[NotificationDelivery] = []
        for role in recipient_roles:
            for ch in self.channels:
                adapter = ADAPTERS.get(ch)
                if adapter is None:
                    out.append(NotificationDelivery(
                        alert_id=alert_id, channel=ch, recipient_role=role,
                        status=DeliveryStatus.NOT_CONFIGURED,
                        mode=ChannelMode.NOT_CONFIGURED,
                        detail=f"No adapter registered for channel {ch!r}."))
                    continue
                out.append(adapter(alert_id, role, subject, body))
        _HTML_BODIES.pop(alert_id, None)
        _SMS_BODIES.pop(alert_id, None)
        return out

    @staticmethod
    def channel_report() -> dict[str, str]:
        """Honest per-channel configuration status, for the cockpit's
        system-status surface."""
        from varuna_alerts.channels.sms_gateway import sms_provider_status

        email_provider = (os.environ.get("VARUNA_EMAIL_PROVIDER") or "").lower()
        has_email = bool(os.environ.get("VARUNA_SMTP_HOST") or email_provider in ("twilio", "resend"))
        
        return {
            "dashboard": ChannelMode.REAL.value,
            "browser_push": ChannelMode.SIMULATED.value,
            "email": ChannelMode.REAL.value if has_email else ChannelMode.NOT_CONFIGURED.value,
            "sms": sms_provider_status()["mode"],
        }
