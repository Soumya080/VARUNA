from dataclasses import asdict
from fastapi import APIRouter, Depends
from apps.api.dependencies import get_alert_service

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

@router.get("/log")
def alert_log(svc = Depends(get_alert_service)):
    log = svc.get_delivery_log()
    return {"items": [asdict(r) for r in log], "count": len(log)}
