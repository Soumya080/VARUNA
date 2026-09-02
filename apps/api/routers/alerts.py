from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies import get_alert_lifecycle_service, get_alert_service
from apps.api.security import get_principal
from varuna_alerts.lifecycle_service import AlertLifecycleService, IllegalAlertTransitionError
from varuna_infra.authorization import AuthorizationError, Principal

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

@router.get("/log")
def alert_log(svc = Depends(get_alert_service)):
    log = svc.get_delivery_log()
    return {"items": [asdict(r) for r in log], "count": len(log)}


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
