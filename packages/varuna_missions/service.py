import uuid
from typing import Optional, List
from datetime import datetime, timezone
from varuna_contracts.schemas import AssetTasking
from varuna_contracts.states import MissionState, MissionRecord
from varuna_missions.repository import InMemoryMissionRepository

class MissionService:
    def __init__(self, repo: InMemoryMissionRepository):
        self._repo = repo

    def create_mission(self, case_id: str, asset_id: str, tasking: AssetTasking) -> MissionRecord:
        mission = MissionRecord(
            mission_id=f"MSN-{uuid.uuid4().hex[:8].upper()}",
            case_id=case_id,
            asset_id=asset_id,
            state=MissionState.AVAILABLE,
        )
        self._repo.save(mission)
        return mission

    def reserve(self, mission_id: str) -> MissionRecord:
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")
        m.transition(MissionState.RESERVED)
        self._repo.save(m)
        return m

    def approve_and_assign(self, mission_id: str, approved_by: str) -> MissionRecord:
        """Human authorization gate. approved_by MUST be set."""
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")
        m.human_approved_by = approved_by
        m.transition(MissionState.ASSIGNED)
        m.assigned_at = datetime.now(timezone.utc)
        self._repo.save(m)
        return m

    def transition(self, mission_id: str, new_state: MissionState, *, reason: Optional[str] = None) -> MissionRecord:
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")
        m.transition(new_state)
        self._repo.save(m)
        return m

    def get(self, mission_id: str) -> Optional[MissionRecord]:
        return self._repo.get(mission_id)
        
    def list_by_case(self, case_id: str) -> List[MissionRecord]:
        return self._repo.list_by_case(case_id)
        
    def list_active(self) -> List[MissionRecord]:
        return self._repo.list_active()
