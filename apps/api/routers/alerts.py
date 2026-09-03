from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies import get_alert_lifecycle_service, get_alert_service
from apps.api.security import get_principal
from varuna_alerts.lifecycle_service import AlertLifecycleService, IllegalAlertTransitionError
from varuna_infra.authorization import AuthorizationError, Principal

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

@router.get("")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    case_id: str | None = None,
    since: str | None = None,
    limit: int = 100,
    offset: int = 0,
    svc: AlertLifecycleService = Depends(get_alert_lifecycle_service),
):
    """Global alert list with filters — the alert history surface.

    Until now the ONLY way to see an alert was to already know its case_id or
    its alert_id, which made an "Alert Center" impossible to build honestly.

    `since` is an ISO-8601 timestamp compared against `created_at`.
    """
    items = svc.list_all()

    if status:
        wanted = {s.strip().lower() for s in status.split(",")}
        items = [a for a in items if a.status.value in wanted]
    if severity:
        wanted = {s.strip().lower() for s in severity.split(",")}
        items = [a for a in items if a.severity.value in wanted]
    if case_id:
        items = [a for a in items if a.case_id == case_id]
    if since:
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"`since` must be ISO-8601, got {since!r}") from exc
        items = [a for a in items if a.created_at >= cutoff]

    items.sort(key=lambda a: a.created_at, reverse=True)
    total = len(items)
    page = items[offset:offset + max(0, limit)]
    return {
        "items": [a.model_dump(mode="json") for a in page],
        "total": total, "limit": limit, "offset": offset,
        "returned": len(page),
    }


@router.get("/log")
def alert_log(svc = Depends(get_alert_service)):
    """Legacy channel delivery-receipt log.

    NOTE: `get_alert_service()` is deliberately NOT a singleton, so this has
    always returned an empty list — the AlertService it reads is constructed
    fresh per request. Rather than paper over that, the real per-alert
    delivery records now live on each AlertRecord's `deliveries` (see
    `GET /v1/alerts`), which is what the cockpit reads. This endpoint is kept
    only so existing callers do not 404, and reports its own emptiness.
    """
    log = svc.get_delivery_log()
    return {
        "items": [asdict(r) for r in log],
        "count": len(log),
        "note": ("Deprecated. This legacy log is per-request and therefore "
                 "always empty. Use GET /v1/alerts — each alert carries its "
                 "own `deliveries` with honest per-channel status."),
    }


# --------------------------------------------------------------------------
# STEP 6: alert lifecycle (docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md,
# items 4/6/7). Case-scoped list lives under /v1/cases to match the router
# `GET /v1/cases/{case_id}` already establishes for other case-scoped
# reads; detail/actions stay under /v1/alerts since an `alert_id` alone
# already identifies the resource.
# --------------------------------------------------------------------------

cases_router = APIRouter(prefix="/v1/cases", tags=["alerts"])


@cases_router.get("/{case_id}/alerts")
def list_case_alerts(case_id: str, svc: AlertLifecycleService = Depends(get_alert_lifecycle_service)):
    return {"items": [a.model_dump(mode="json") for a in svc.list_by_case(case_id)]}


@router.get("/{alert_id}")
def get_alert(alert_id: str, svc: AlertLifecycleService = Depends(get_alert_lifecycle_service)):
    alert = svc.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.model_dump(mode="json")


def _handle_transition(fn, alert_id: str):
    try:
        alert = fn(alert_id)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IllegalAlertTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return alert.model_dump(mode="json")


@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    svc: AlertLifecycleService = Depends(get_alert_lifecycle_service),
    principal: Principal = Depends(get_principal),
):
    return _handle_transition(lambda aid: svc.acknowledge(aid, principal=principal), alert_id)


@router.post("/{alert_id}/escalate")
def escalate_alert(
    alert_id: str,
    svc: AlertLifecycleService = Depends(get_alert_lifecycle_service),
    principal: Principal = Depends(get_principal),
):
    return _handle_transition(lambda aid: svc.escalate(aid, principal=principal), alert_id)


@router.post("/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    svc: AlertLifecycleService = Depends(get_alert_lifecycle_service),
    principal: Principal = Depends(get_principal),
):
    return _handle_transition(lambda aid: svc.resolve(aid, principal=principal), alert_id)


# --------------------------------------------------------------------------
# Credential verification (Phase 3). Lets an operator confirm SMTP/SMS really
# work without fabricating a case or waiting for a material change.
# --------------------------------------------------------------------------

class TestNotificationRequest(BaseModel):
    role: str = Field("duty_officer",
                      description="Operational role to notify, per configs/recipients.yaml")
    channels: list[str] | None = Field(
        None, description="Channels to try; defaults to email + sms.")


@router.post("/test-notification")
def test_notification(
    body: TestNotificationRequest,
    principal: Principal = Depends(get_principal),
):
    """Send a REAL notification to verify credentials.

    Admin-only, because it costs money and reaches real people. The message
    is explicitly marked as a test in its own body — it must never be
    mistakable for a live operational alert.

    Returns exactly what each channel reported. A NOT_CONFIGURED result is a
    successful call with an honest answer, not an error.
    """
    from varuna_alerts.channel_orchestrator import ChannelOrchestrator
    from varuna_infra.authorization import authorize
    from varuna_infra.rbac import Permission

    try:
        authorize(principal, Permission.TEST_NOTIFICATION,
                  operation="alerts.test_notification", subject_id=body.role)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    probe = {
        "alert_id": "TEST-NOTIFICATION",
        "case_id": "VARUNA-CONNECTIVITY-TEST",
        "severity": "info",
        "event_type": "notification.test",
        "material_dimension": "notification.test",
        "reason": (f"Connectivity test requested by {principal.principal_id}. "
                   "This is NOT a spill alert and requires no action."),
        "severity_basis": "operator-initiated credential verification",
        "engine_mode": "test",
        "is_simulated": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "evidence_refs": [],
        "routing": {},
    }

    orch = ChannelOrchestrator(channels=body.channels or ["email", "sms"])
    deliveries = orch.deliver(
        alert_id="TEST-NOTIFICATION", recipient_roles=[body.role],
        subject="[VARUNA TEST] notification connectivity check",
        body=probe["reason"], alert=probe,
    )
    return {
        "requested_by": principal.principal_id,
        "role": body.role,
        "channels": ChannelOrchestrator.channel_report(),
        "results": [d.model_dump(mode="json") for d in deliveries],
    }
