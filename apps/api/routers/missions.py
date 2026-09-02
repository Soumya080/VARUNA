from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies import get_mission_service
from apps.api.security import get_principal
from varuna_infra.authorization import AuthorizationError, Principal
from varuna_missions.service import MissionService

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


@router.get("/{mission_id}/audit")
def get_mission_audit(mission_id: str, svc: MissionService = Depends(get_mission_service)):
    """STEP 6 (docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md, item 12): the
    authorization decisions `approve_and_assign()` already records were
    previously discarded every request because a fresh `MissionService`
    (and therefore a fresh, empty `AuditLog`) was constructed per call.
    Now that `get_mission_service()` is a singleton, this is answerable:
    who was allowed, who was denied, and when, for this mission —
    both approvals AND denials, since `AuditLog.for_subject` records both."""
    m = svc.get(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    entries = svc.audit_log.for_subject(mission_id)
    return {"items": [e.model_dump(mode="json") for e in entries]}


class ApproveMissionRequest(BaseModel):
    """`approved_by` must equal the authenticated principal — MissionService
    rejects a mismatch so an authorized caller cannot record someone else as
    the approver of a physical dispatch."""
    approved_by: str = Field(..., min_length=1)


@router.post("/{mission_id}/approve")
def approve_mission(
    mission_id: str,
    body: ApproveMissionRequest,
    svc: MissionService = Depends(get_mission_service),
    principal: Principal = Depends(get_principal),
):
    """Two-step human authorization gate for dispatching an asset.

    Identity now comes from `apps.api.security.get_principal` — a verified
    JWT, or (demo_mode only) the previous unsigned header pair — rather than
    a header-only resolver local to this router. See that module's docstring
    for why the header path is now demo_mode-gated instead of always-on.
    """
    try:
        mission = svc.approve_and_assign(
            mission_id, approved_by=body.approved_by, principal=principal)
    except AuthorizationError as exc:
        # 403, not 404: the mission exists and the caller is simply not
        # permitted. Masking that as "not found" would hide a real
        # authorization failure from the audit trail the operator reads.
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    return mission.model_dump(mode="json")
