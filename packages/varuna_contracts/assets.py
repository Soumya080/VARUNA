"""
VARUNA GRID — Asset & duty-personnel registry contracts (Phase 4).

Kept in a separate module from `schemas.py` deliberately: these types are
new (2026-09), not part of the original locked cross-subsystem contract, and
splitting them out avoids growing that file's already-large surface for a
feature that only `varuna_assets`/`varuna_missions` consume.

Relationship to the EXISTING `AssetType`/`AssetTasking` in `schemas.py`:
those are unchanged and still mean what they always meant (a tasking plan's
declared asset *type* and a bare `base_name` string). `Asset` here is the
richer, individually-identified registry entry a real assignment workflow
picks from; `ASSET_KIND_TO_TYPE` is the one place that bridges the two, used
only when building an `AssetTasking` from a selected `Asset` — nothing
upstream of that bridge is renamed or broken.

`Asset`/`DutyPersonnel` data is explicitly illustrative, Indian-Coast-Guard-
style demo data (see `varuna_assets/seed.py`) — VARUNA has no access to, and
must never simulate having access to, a real live duty roster or fleet
status feed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from varuna_contracts.schemas import AssetType, GeoPoint

__all__ = [
    "Asset",
    "AssetKind",
    "AssetStatus",
    "ASSET_KIND_TO_TYPE",
    "DutyPersonnel",
    "DutyRole",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AssetKind(StrEnum):
    OPV = "opv"                      # Offshore Patrol Vessel
    FPV = "fpv"                      # Fast Patrol Vessel
    INTERCEPTOR_BOAT = "interceptor_boat"
    DORNIER_228 = "dornier_228"
    RUAV_HERON = "ruav_heron"
    STATION_BOAT = "station_boat"


#: Bridge to the existing, locked `AssetType` (3 values) — used ONLY when
#: constructing an `AssetTasking` from a selected `Asset`. `AssetTasking`
#: itself is untouched.
ASSET_KIND_TO_TYPE: dict[AssetKind, AssetType] = {
    AssetKind.OPV: AssetType.OPV,
    AssetKind.FPV: AssetType.OPV,               # no finer-grained AssetType exists; nearest real mapping
    AssetKind.INTERCEPTOR_BOAT: AssetType.OPV,
    AssetKind.DORNIER_228: AssetType.DORNIER,
    AssetKind.RUAV_HERON: AssetType.DORNIER,     # both are air assets; AssetType has no separate UAV value
    AssetKind.STATION_BOAT: AssetType.STATION_BOAT,
}


class AssetStatus(StrEnum):
    AVAILABLE = "available"
    DEPLOYED = "deployed"
    MAINTENANCE = "maintenance"
    UNAVAILABLE = "unavailable"


class Asset(_Base):
    asset_id: str
    name: str                                    # e.g. "ICGS Varad"
    kind: AssetKind
    home_base: str                                # e.g. "Mumbai"
    status: AssetStatus = AssetStatus.AVAILABLE
    current_position: GeoPoint | None = None
    endurance_hours: float | None = Field(None, gt=0)
    crew_size: int | None = Field(None, ge=0)  # 0 is real — e.g. an unmanned RUAV
    notes: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DutyRole(StrEnum):
    """Deliberately reuses `varuna_alerts.routing_policy.OperationalRole`'s
    vocabulary for the three roles that can hold a physical duty shift
    (external stakeholders like dg_shipping/state_pcb are notified but never
    staff a duty roster, so they're not here)."""
    DUTY_OFFICER = "duty_officer"
    SUPERVISOR = "supervisor"
    FIELD_OPERATOR = "field_operator"


class DutyPersonnel(_Base):
    personnel_id: str
    name: str
    rank: str | None = None                       # illustrative rank title, not verified credentials
    role: DutyRole
    base: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    on_duty: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
