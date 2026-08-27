from fastapi import APIRouter, Depends
from apps.api.config import settings
from apps.api.dependencies import get_workflow, get_mission_service, get_alert_service

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])

@router.get("/summary")
def dashboard_summary(
    workflow = Depends(get_workflow),
    mission_svc = Depends(get_mission_service),
    alert_svc = Depends(get_alert_service),
):
    cases = workflow.cases.list_all()
    active_missions = mission_svc.list_active()
    alert_log = alert_svc.get_delivery_log()
    return {
        "total_cases": len(cases),
        "active_cases": len([c for c in cases if c.status.value not in ("completed", "failed", "quarantined")]),
        "active_missions": len(active_missions),
        "total_alerts_sent": len([a for a in alert_log if a.status == "sent"]),
        "scientific_status": settings.scientific_status,
    }
