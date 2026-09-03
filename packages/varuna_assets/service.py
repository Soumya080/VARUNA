from __future__ import annotations

from varuna_assets.repository import InMemoryAssetRepository, InMemoryPersonnelRepository
from varuna_contracts.assets import Asset, AssetStatus, DutyPersonnel


class AssetService:
    def __init__(self, repo: InMemoryAssetRepository):
        self._repo = repo

    def list_available(self, kind: str | None = None) -> list[Asset]:
        return self._repo.list_available(kind)

    def list_all(self) -> list[Asset]:
        return self._repo.all()

    def get(self, asset_id: str) -> Asset | None:
        return self._repo.get(asset_id)

    def set_status(self, asset_id: str, status: AssetStatus) -> Asset:
        asset = self._repo.get(asset_id)
        if asset is None:
            raise ValueError(f"Asset {asset_id} not found")
        asset = asset.model_copy(update={"status": status})
        self._repo.save(asset)
        return asset


class PersonnelService:
    def __init__(self, repo: InMemoryPersonnelRepository):
        self._repo = repo

    def list_on_duty(self, role: str | None = None) -> list[DutyPersonnel]:
        return self._repo.list_on_duty(role)

    def list_all(self) -> list[DutyPersonnel]:
        return self._repo.all()

    def get(self, personnel_id: str) -> DutyPersonnel | None:
        return self._repo.get(personnel_id)
