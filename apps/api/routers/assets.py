"""
VARUNA — Asset & duty-personnel registry endpoints (Phase 4).

Read-only for now; asset status changes and the personnel roster are seeded
illustrative data (see packages/varuna_assets/seed.py), not a live feed —
these endpoints never claim otherwise.
"""
from fastapi import APIRouter, Depends

from apps.api.dependencies import get_asset_service, get_personnel_service
from varuna_assets.service import AssetService, PersonnelService

router = APIRouter(tags=["assets"])


@router.get("/v1/assets")
def list_assets(status: str | None = None, kind: str | None = None,
                 svc: AssetService = Depends(get_asset_service)):
    """`status=available` is the common case (asset-picker for a new
    mission); omit it to see the full fleet, including deployed/maintenance."""
    items = svc.list_available(kind) if status == "available" else svc.list_all()
    if status and status != "available":
        items = [a for a in items if a.status.value == status]
    return {"items": [a.model_dump(mode="json") for a in items]}


@router.get("/v1/assets/{asset_id}")
def get_asset(asset_id: str, svc: AssetService = Depends(get_asset_service)):
    from fastapi import HTTPException
    a = svc.get(asset_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Unknown asset {asset_id!r}")
    return a.model_dump(mode="json")


@router.get("/v1/personnel")
def list_personnel(role: str | None = None, on_duty_only: bool = False,
                    svc: PersonnelService = Depends(get_personnel_service)):
    items = svc.list_on_duty(role) if on_duty_only else svc.list_all()
    if role and not on_duty_only:
        items = [p for p in items if p.role.value == role]
    return {"items": [p.model_dump(mode="json") for p in items]}
