from fastapi import APIRouter, Depends, HTTPException
from varuna_missions.service import MissionService
from apps.api.dependencies import get_mission_service

router = APIRouter(prefix="/v1/missions", tags=["missions"])

@router.get("")
def list_missions(svc: MissionService = Depends(get_mission_service)):
    missions = svc.list_active()
    return {"items": [m.model_dump(mode="json") for m in missions]}

@router.get("/{mission_id}")
def get_mission(mission_id: str, svc: MissionService = Depends(get_mission_service)):
    m = svc.get(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    return m.model_dump(mode="json")
