"""VARUNA GRID — Asset & duty-personnel registry (Phase 4).

Additive package. Does not modify `varuna_missions` — `AssetService`/
`PersonnelService` here are consulted by the mission-creation API to
validate an operator's asset/officer choice; the mission FSM itself stays
entirely owned by `varuna_missions`.
"""
from varuna_assets.service import AssetService, PersonnelService

__all__ = ["AssetService", "PersonnelService"]
