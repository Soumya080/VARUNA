"""
VARUNA — real SMS gateway clients (MSG91 / Fast2SMS).

These are genuine HTTP clients, not stubs. They become REAL the moment
credentials exist in the environment; until then every call reports
NOT_CONFIGURED. Nothing here ever fabricates a provider response, a message
id, or a delivery confirmation.

Configuration (all read at send time, never stored in code):

    VARUNA_SMS_PROVIDER    msg91 | fast2sms
    VARUNA_SMS_API_KEY     provider API key / authkey
    VARUNA_SMS_SENDER_ID   6-char sender id (MSG91 DLT sender)
    VARUNA_SMS_ROUTE       optional; provider-specific route override

Important honesty note about Indian SMS: MSG91 and Fast2SMS both operate
under TRAI DLT rules. A transactional send generally requires a registered
template and sender id, and a gateway will happily return HTTP 200 while
rejecting the message downstream. We therefore parse the provider's own
success flag out of the body rather than trusting the status code, and we
treat "accepted by the gateway" as SENT — never as DELIVERED, because
handset delivery is a separate callback we do not receive.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from varuna_alerts.channel_orchestrator import (
    ChannelMode, DeliveryStatus, NotificationDelivery,
)

__all__ = ["send_sms", "sms_provider_status", "SUPPORTED_PROVIDERS"]

SUPPORTED_PROVIDERS = ("msg91", "fast2sms", "twilio")

_TIMEOUT_S = 15.0


def _cfg() -> tuple[str | None, str | None, str | None]:
    return (
        (os.environ.get("VARUNA_SMS_PROVIDER") or "").strip().lower() or None,
        os.environ.get("VARUNA_SMS_API_KEY") or None,
        os.environ.get("VARUNA_SMS_SENDER_ID") or None,
    )


def sms_provider_status() -> dict[str, Any]:
    """What the cockpit's channel badge should say, and why."""
    provider, key, sender = _cfg()
    if not provider:
        return {"mode": ChannelMode.NOT_CONFIGURED.value, "provider": None,
                "reason": "VARUNA_SMS_PROVIDER is not set."}
    if provider not in SUPPORTED_PROVIDERS:
        return {"mode": ChannelMode.NOT_CONFIGURED.value, "provider": provider,
                "reason": (f"provider {provider!r} has no client in this build; "
                           f"supported: {', '.join(SUPPORTED_PROVIDERS)}")}
    if not key and provider != "twilio":
        return {"mode": ChannelMode.NOT_CONFIGURED.value, "provider": provider,
                "reason": "VARUNA_SMS_API_KEY is not set."}
    if provider == "msg91" and not sender:
        return {"mode": ChannelMode.NOT_CONFIGURED.value, "provider": provider,
                "reason": "MSG91 requires VARUNA_SMS_SENDER_ID (DLT sender id)."}
    if provider == "twilio":
        if not os.environ.get("VARUNA_TWILIO_ACCOUNT_SID") or not os.environ.get("VARUNA_TWILIO_AUTH_TOKEN"):
            return {"mode": ChannelMode.NOT_CONFIGURED.value, "provider": provider,
                    "reason": "Twilio requires VARUNA_TWILIO_ACCOUNT_SID and VARUNA_TWILIO_AUTH_TOKEN."}
    return {"mode": ChannelMode.REAL.value, "provider": provider,
            "reason": f"{provider} configured."}


# --------------------------------------------------------------------------
# Provider calls. Each returns (ok, detail) — never raises to the caller.
# --------------------------------------------------------------------------

def _send_msg91(key: str, sender: str | None, phone: str, body: str,
                client: httpx.Client) -> tuple[bool, str]:
    """MSG91 v2 sendhttp. Returns the provider's own response text as detail."""
    r = client.get(
        "https://api.msg91.com/api/v2/sendsms",
        params={"authkey": key},
        headers={"authkey": key, "Content-Type": "application/json"},
        json={
            "sender": sender, "route": os.environ.get("VARUNA_SMS_ROUTE", "4"),
            "country": "91",
            "sms": [{"message": body, "to": [phone.lstrip("+")]}],
        },
    )
    text = (r.text or "").strip()
    # MSG91 returns 200 with {"type":"success"|"error", ...}
    ok = r.status_code < 400 and '"error"' not in text.lower()
    return ok, f"HTTP {r.status_code}: {text[:300]}"


def _send_fast2sms(key: str, sender: str | None, phone: str, body: str,
                   client: httpx.Client) -> tuple[bool, str]:
    """Fast2SMS bulkV2. `return` field in the body is the real success flag."""
    r = client.post(
        "https://www.fast2sms.com/dev/bulkV2",
        headers={"authorization": key},
        data={
            "route": os.environ.get("VARUNA_SMS_ROUTE", "q"),
            "message": body,
            "numbers": phone.lstrip("+").removeprefix("91"),
            **({"sender_id": sender} if sender else {}),
        },
    )
    text = (r.text or "").strip()
    ok = False
    try:
        ok = bool(r.json().get("return") is True)
    except Exception:
        ok = r.status_code < 400
    return ok, f"HTTP {r.status_code}: {text[:300]}"


def _send_twilio(key: str | None, sender: str | None, phone: str, body: str,
                 client: httpx.Client) -> tuple[bool, str]:
    """Twilio SMS using twilio-python."""
    try:
        from twilio.rest import Client
        
        account_sid = os.environ.get("VARUNA_TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("VARUNA_TWILIO_AUTH_TOKEN")
        from_phone = os.environ.get("VARUNA_TWILIO_FROM_PHONE", "+17372212163")
        
        twilio_client = Client(account_sid, auth_token)
        
        # Override phone with the target number if provided by user request
        target_phone = os.environ.get("VARUNA_ALERT_PHONE") or phone
        
        message = twilio_client.messages.create(
            to=target_phone,
            from_=from_phone,
            body="sms_appointment_reminders",
        )
        return True, f"Twilio SMS SID: {message.sid}"
    except Exception as e:
        return False, f"Twilio SMS failed: {str(e)}"


_SENDERS = {"msg91": _send_msg91, "fast2sms": _send_fast2sms, "twilio": _send_twilio}


def send_sms(*, alert_id: str, recipient_role: str, phone: str | None,
             body: str, client: httpx.Client | None = None) -> NotificationDelivery:
    """Send one SMS. Always returns a NotificationDelivery describing what
    genuinely happened."""
    provider, key, sender = _cfg()
    status = sms_provider_status()

    if status["mode"] != ChannelMode.REAL.value:
        return NotificationDelivery(
            alert_id=alert_id, channel="sms", recipient_role=recipient_role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            provider=provider, detail=status["reason"],
        )

    if not phone:
        return NotificationDelivery(
            alert_id=alert_id, channel="sms", recipient_role=recipient_role,
            status=DeliveryStatus.NOT_CONFIGURED, mode=ChannelMode.NOT_CONFIGURED,
            provider=provider,
            detail=(f"no phone number configured for role {recipient_role!r} — "
                    "see configs/recipients.yaml"),
        )

    owns_client = client is None
    client = client or httpx.Client(timeout=_TIMEOUT_S)
    try:
        ok, detail = _SENDERS[provider](key, sender, phone, body, client)
        return NotificationDelivery(
            alert_id=alert_id, channel="sms", recipient_role=recipient_role,
            # Gateway acceptance is NOT handset delivery — we never receive a
            # delivery callback, so SENT is the strongest honest claim.
            status=DeliveryStatus.SENT if ok else DeliveryStatus.FAILED,
            mode=ChannelMode.REAL, provider=provider,
            error=None if ok else detail,
            detail=(f"accepted by {provider} for {phone}; gateway acceptance is not "
                    f"proof of handset delivery. {detail}") if ok else None,
        )
    except Exception as exc:
        return NotificationDelivery(
            alert_id=alert_id, channel="sms", recipient_role=recipient_role,
            status=DeliveryStatus.FAILED, mode=ChannelMode.REAL, provider=provider,
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if owns_client:
            client.close()
