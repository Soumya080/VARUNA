from pathlib import Path
from typing import Dict, List, Optional

from varuna_contracts.states import MissionRecord, MissionState


class InMemoryMissionRepository:
    """Mission storage.

    Name kept for the existing call sites, but optionally disk-backed: pass
    `path=` and mission state — including `human_approved_by`, `assigned_at`
    and the full `state_history` — survives an API restart. A mission
    approval is a record of a human authorising a physical dispatch; losing
    it on a process restart is not acceptable for an auditable system.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._missions: Dict[str, MissionRecord] = {}
        self._store = None
        if path is not None:
            from varuna_infra.jsonl_store import KeyedJsonlStore

            self._store = KeyedJsonlStore(
                path,
                key=lambda m: m.mission_id,
                loads=MissionRecord.model_validate_json,
                dumps=lambda m: m.model_dump_json(),
            )
            for mission in self._store.all():
                self._missions[mission.mission_id] = mission

    @property
    def load_errors(self) -> int:
        return getattr(self._store, "load_errors", 0)

    @property
    def persisted(self) -> bool:
        return self._store is not None

    def save(self, mission: MissionRecord) -> None:
        self._missions[mission.mission_id] = mission
        if self._store is not None:
            self._store.put(mission)

    def get(self, mission_id: str) -> Optional[MissionRecord]:
        return self._missions.get(mission_id)

    def list_by_case(self, case_id: str) -> List[MissionRecord]:
        return [m for m in self._missions.values() if m.case_id == case_id]

    def list_active(self) -> List[MissionRecord]:
        terminal = {MissionState.COMPLETE, MissionState.CLOSED}
        return [m for m in self._missions.values() if m.state not in terminal]

    def all(self) -> List[MissionRecord]:
        """Every mission including terminal ones — mission history."""
        return list(self._missions.values())
