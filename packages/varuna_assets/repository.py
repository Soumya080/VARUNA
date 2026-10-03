"""Asset/personnel storage — mirrors `varuna_missions.repository.
InMemoryMissionRepository`'s shape exactly (save/get/list methods,
optional `KeyedJsonlStore` persistence) so the two registries feel like one
consistent pattern rather than two.
"""
from __future__ import annotations

from pathlib import Path

from varuna_contracts.assets import Asset, AssetStatus, DutyPersonnel


class InMemoryAssetRepository:
    def __init__(self, path: str | Path | None = None, seed: list[Asset] | None = None) -> None:
        self._assets: dict[str, Asset] = {}
        self._store = None
        if path is not None:
            from varuna_infra.jsonl_store import KeyedJsonlStore

            self._store = KeyedJsonlStore(
                path, key=lambda a: a.asset_id,
                loads=Asset.model_validate_json, dumps=lambda a: a.model_dump_json(),
            )
            for asset in self._store.all():
                self._assets[asset.asset_id] = asset

        # Seed only when the store is genuinely empty — never overwrite a
        # real operator-made status change (e.g. AVAILABLE -> DEPLOYED) with
        # stale seed data on every restart.
        if not self._assets and seed:
            for asset in seed:
                self.save(asset)

    @property
    def load_errors(self) -> int:
        return getattr(self._store, "load_errors", 0)

    def save(self, asset: Asset) -> None:
        self._assets[asset.asset_id] = asset
        if self._store is not None:
            self._store.put(asset)

    def get(self, asset_id: str) -> Asset | None:
        return self._assets.get(asset_id)

    def list_available(self, kind: str | None = None) -> list[Asset]:
        items = [a for a in self._assets.values() if a.status == AssetStatus.AVAILABLE]
        if kind:
            items = [a for a in items if a.kind.value == kind]
        return items

    def all(self) -> list[Asset]:
        return list(self._assets.values())


class InMemoryPersonnelRepository:
    def __init__(self, path: str | Path | None = None, seed: list[DutyPersonnel] | None = None) -> None:
        self._people: dict[str, DutyPersonnel] = {}
        self._store = None
        if path is not None:
            from varuna_infra.jsonl_store import KeyedJsonlStore

            self._store = KeyedJsonlStore(
                path, key=lambda p: p.personnel_id,
                loads=DutyPersonnel.model_validate_json, dumps=lambda p: p.model_dump_json(),
            )
            for person in self._store.all():
                self._people[person.personnel_id] = person

        if not self._people and seed:
            for person in seed:
                self.save(person)

    @property
    def load_errors(self) -> int:
        return getattr(self._store, "load_errors", 0)

    def save(self, person: DutyPersonnel) -> None:
        self._people[person.personnel_id] = person
        if self._store is not None:
            self._store.put(person)

    def get(self, personnel_id: str) -> DutyPersonnel | None:
        return self._people.get(personnel_id)

    def list_on_duty(self, role: str | None = None) -> list[DutyPersonnel]:
        items = [p for p in self._people.values() if p.on_duty]
        if role:
            items = [p for p in items if p.role.value == role]
        return items

    def all(self) -> list[DutyPersonnel]:
        return list(self._people.values())
