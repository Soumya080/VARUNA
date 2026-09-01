from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies import get_mission_service
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


class ApproveMissionRequest(BaseModel):
    """`approved_by` must equal the authenticated principal — MissionService
    rejects a mismatch so an authorized caller cannot record someone else as
    the approver of a physical dispatch."""
    approved_by: str = Field(..., min_length=1)


def _principal(x_user_id: str | None, x_user_role: str | None) -> Principal:
    """
    Resolve the calling principal from request headers.

    INTERIM MECHANISM, stated plainly rather than left to be discovered: this
    trusts `X-User-Id`/`X-User-Role` headers. `varuna_infra.auth` already
    implements signed JWTs (`verify_token`), and this endpoint should move to
    them before any deployment outside a trusted network. It is wired this way
    now because no login/token-issuing route exists yet, and shipping the
    authorization CHECK (which was entirely absent) is the security-relevant
    half; header spoofing is a weaker gap than having no permission check at
    all, but it is still a gap and is tracked as one.
    """
    if not x_user_id or not x_user_role:
        raise HTTPException(
            status_code=401,
            detail="X-User-Id and X-User-Role headers are required to approve a mission",
        )
    return Principal(principal_id=x_user_id, role=x_user_role)


@router.post("/{mission_id}/approve")
def approve_mission(
    mission_id: str,
    body: ApproveMissionRequest,
    svc: MissionService = Depends(get_mission_service),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    """Two-step human authorization gate for dispatching an asset."""
    principal = _principal(x_user_id, x_user_role)
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
