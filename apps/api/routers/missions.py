from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies import get_asset_service, get_mission_service
from apps.api.security import get_principal
from varuna_assets.service import AssetService
from varuna_contracts.assets import AssetStatus
from varuna_contracts.schemas import AssetTasking
from varuna_infra.authorization import AuthorizationError, Principal, authorize
from varuna_infra.rbac import Permission
from varuna_contracts.states import MISSION_TRANSITIONS, MissionState
from varuna_missions.service import MissionService

router = APIRouter(prefix="/v1/missions", tags=["missions"])

@router.get("")
def list_missions(svc: MissionService = Depends(get_mission_service)):
    missions = svc.list_active()
    return {"items": [m.model_dump(mode="json") for m in missions]}


class CreateMissionRequest(BaseModel):
    case_id: str = Field(..., min_length=1)
    asset_id: str = Field(..., min_length=1)
    tasking: AssetTasking | None = None


@router.post("")
def create_mission(
    body: CreateMissionRequest,
    svc: MissionService = Depends(get_mission_service),
    assets: AssetService = Depends(get_asset_service),
    principal: Principal = Depends(get_principal),
):
    """Phase 4 — the previously-missing `POST /v1/missions`: an operator
    picks a real, currently-available `Asset` (from `GET /v1/assets`) and
    this creates a PROPOSED (state=AVAILABLE) mission against it. This is
    NOT the approval step — `POST /{mission_id}/approve` remains the one
    place a physical dispatch is actually authorized, per
    `MissionService.approve_and_assign()`'s two-step gate.
    """
    try:
        authorize(principal, Permission.CREATE_MISSION,
                  operation="mission.create", subject_id=body.case_id)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    asset = assets.get(body.asset_id)
    if asset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown asset {body.asset_id!r}. See GET /v1/assets for real, valid ids.")
    if asset.status != AssetStatus.AVAILABLE:
        raise HTTPException(
            status_code=409,
            detail=f"Asset {body.asset_id!r} is {asset.status.value}, not available.")

    mission = svc.create_mission(body.case_id, body.asset_id, tasking=body.tasking)
    return mission.model_dump(mode="json")

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


# --------------------------------------------------------------------------
# Mission FSM (ADR-0015). Ten states existed with zero routes — nothing could
# advance a mission past ASSIGNED, while the frontend already rendered
# en_route / on_station / complete badges the system could never produce.
# --------------------------------------------------------------------------

class TransitionRequest(BaseModel):
    to_state: str = Field(..., description="Target MissionState, e.g. 'acknowledged'")
    reason: str | None = Field(
        None, description="Why. Recorded on the mission; for a physical "
                          "dispatch this is the important half.")


@router.get("/{mission_id}/transitions")
def legal_transitions(mission_id: str, svc: MissionService = Depends(get_mission_service)):
    """What this mission can legally do next.

    Lets a UI render only reachable actions instead of offering every state
    and discovering illegality by 409.
    """
    m = svc.get(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {
        "mission_id": mission_id,
        "state": m.state.value,
        "legal_next": sorted(s.value for s in MISSION_TRANSITIONS[m.state]),
        "terminal": not MISSION_TRANSITIONS[m.state],
    }


@router.post("/{mission_id}/transition")
def transition_mission(
    mission_id: str,
    body: TransitionRequest,
    svc: MissionService = Depends(get_mission_service),
    principal: Principal = Depends(get_principal),
):
    """Advance a mission through its state machine.

    One route rather than ten per-verb endpoints: each of those would be
    another chance to forget the authorization call, whereas this validates
    against MISSION_TRANSITIONS in a single place. Authorization happens
    before any mutation, so a denial leaves the mission untouched.
    """
    try:
        target = MissionState(body.to_state.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(f"unknown mission state {body.to_state!r}. Valid: "
                    f"{sorted(s.value for s in MissionState)}"),
        ) from exc

    try:
        mission = svc.transition(mission_id, target,
                                 principal=principal, reason=body.reason)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        # An illegal FSM edge is a conflict with current state, not bad input.
        raise HTTPException(status_code=409, detail=msg) from exc
    return mission.model_dump(mode="json")


@router.post("/{mission_id}/cancel")
def cancel(
    mission_id: str,
    body: TransitionRequest | None = None,
    svc: MissionService = Depends(get_mission_service),
    principal: Principal = Depends(get_principal),
):
    """Cancel an assigned mission: REASSIGNED -> CLOSED.

    Wires the previously unrouted `varuna_missions.lifecycle_view.cancel_mission`.
    An AVAILABLE or RESERVED mission cannot be cancelled — the locked FSM
    defines no such edge, and that refusal is honest rather than a fabricated
    transition.
    """
    from varuna_missions.lifecycle_view import MissionNotCancellableError, cancel_mission

    try:
        mission = cancel_mission(svc, mission_id, principal=principal,
                                 reason=(body.reason if body else None))
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except MissionNotCancellableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return mission.model_dump(mode="json")


@router.get("/{mission_id}/history")
def mission_history(mission_id: str, svc: MissionService = Depends(get_mission_service)):
    """State history with the reason recorded for each change."""
    m = svc.get(mission_id)
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    reasons = dict(m.state_change_reasons or [])
    return {
        "mission_id": mission_id,
        "current_state": m.state.value,
        "history": [
            {"state": st, "at": str(at), "reason": reasons.get(st)}
            for st, at in (m.state_history or [])
        ],
        "human_approved_by": m.human_approved_by,
        "assigned_at": str(m.assigned_at) if m.assigned_at else None,
    }
