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
        """Human authorization gate. approved_by MUST be set.

        MISSION_TRANSITIONS (varuna_contracts/states.py) has no direct
        AVAILABLE -> ASSIGNED edge; a freshly-created (PROPOSED) mission is
        AVAILABLE and must pass through RESERVED first. Calling
        `m.transition(ASSIGNED)` straight from AVAILABLE was previously
        illegal and raised on every first-time approval. For a mission
        already RESERVED (e.g. re-approval after a prior release), the
        reserve step is skipped rather than attempted twice.
        """
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")
        if m.state is MissionState.AVAILABLE:
            m.transition(MissionState.RESERVED)
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
