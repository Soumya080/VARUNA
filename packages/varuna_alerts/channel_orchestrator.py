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
  whatsapp         NOT_CONFIGURED (adapter shape only)
  zoho_cliq        NOT_CONFIGURED (optional adapter; explicitly NOT in the
                                   critical path, per the target architecture)
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
    host = os.environ.get("VARUNA_SMTP_HOST")
    if not host:
        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            detail="VARUNA_SMTP_HOST is not set — no SMTP server configured, nothing sent.",
        )
    try:
        import smtplib
        from email.message import EmailMessage

        to_addr = os.environ.get("VARUNA_ALERT_TO")
        from_addr = os.environ.get("VARUNA_ALERT_FROM", "varuna-alerts@localhost")
        if not to_addr:
            return NotificationDelivery(
                alert_id=alert_id, channel="email", recipient_role=role,
                status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
                provider=host,
                detail="VARUNA_SMTP_HOST is set but VARUNA_ALERT_TO is not — no recipient.",
            )
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, from_addr, to_addr
        msg.set_content(body)
        port = int(os.environ.get("VARUNA_SMTP_PORT", "25"))
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.send_message(msg)
        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.SENT, mode=ChannelMode.REAL, provider=f"smtp://{host}:{port}",
            detail=f"Handed to SMTP for {to_addr}. SMTP acceptance is not proof of inbox delivery.",
        )
    except Exception as exc:
        return NotificationDelivery(
            alert_id=alert_id, channel="email", recipient_role=role,
            status=DeliveryStatus.FAILED, mode=ChannelMode.REAL, provider=host,
            error=f"{type(exc).__name__}: {exc}",
        )


def _sms(alert_id: str, role: str, subject: str, body: str) -> NotificationDelivery:
    provider = os.environ.get("VARUNA_SMS_PROVIDER")
    key = os.environ.get("VARUNA_SMS_API_KEY")
    if not provider or not key:
        return NotificationDelivery(
            alert_id=alert_id, channel="sms", recipient_role=role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            detail=("VARUNA_SMS_PROVIDER / VARUNA_SMS_API_KEY are not set — no SMS gateway "
                    "configured, nothing sent."),
        )
    # A configured provider would be called here. Deliberately not faked:
    # there is no provider integration in this repository, so a configured
    # environment still reports honestly rather than claiming a send.
    return NotificationDelivery(
        alert_id=alert_id, channel="sms", recipient_role=role,
        status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
        provider=provider,
        detail=(f"Provider {provider!r} is named in the environment but no client for it is "
                "implemented in this repository, so no send was attempted."),
    )


def _unimplemented(channel: str, note: str):
    def _adapter(alert_id: str, role: str, subject: str, body: str) -> NotificationDelivery:
        return NotificationDelivery(
            alert_id=alert_id, channel=channel, recipient_role=role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            detail=note,
        )
    return _adapter


ADAPTERS = {
    "dashboard": _dashboard,
    "browser_push": _browser_push,
    "email": _email,
    "sms": _sms,
    "whatsapp": _unimplemented(
        "whatsapp", "Adapter shape only — no WhatsApp Business API credentials or client."),
    "zoho_cliq": _unimplemented(
        "zoho_cliq", "Optional adapter, deliberately NOT in the critical path. Not configured."),
}

#: Channels attempted for every alert, in priority order. Dashboard first so
#: the operator surface is always populated even when nothing external is
#: configured.
DEFAULT_CHANNELS = ["dashboard", "browser_push", "email", "sms"]


class ChannelOrchestrator:
    def __init__(self, channels: list[str] | None = None):
        self.channels = channels or list(DEFAULT_CHANNELS)

    def deliver(self, *, alert_id: str, recipient_roles: list[str], subject: str,
                body: str) -> list[NotificationDelivery]:
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
        return out

    @staticmethod
    def channel_report() -> dict[str, str]:
        """Honest per-channel configuration status, for the cockpit's
        system-status surface."""
        probe = {ch: ADAPTERS[ch]("probe", "duty_officer", "probe", "probe")
                 for ch in ADAPTERS if ch != "email"}
        report = {ch: d.mode.value for ch, d in probe.items()}
        report["email"] = (ChannelMode.REAL.value if os.environ.get("VARUNA_SMTP_HOST")
                           else ChannelMode.NOT_CONFIGURED.value)
        return report
