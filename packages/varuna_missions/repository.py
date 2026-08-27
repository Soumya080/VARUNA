from typing import List, Optional, Dict
from varuna_contracts.states import MissionState, MissionRecord

class InMemoryMissionRepository:
    def __init__(self):
        self._missions: Dict[str, MissionRecord] = {}

    def save(self, mission: MissionRecord) -> None:
        self._missions[mission.mission_id] = mission

    def get(self, mission_id: str) -> Optional[MissionRecord]:
        return self._missions.get(mission_id)

    def list_by_case(self, case_id: str) -> List[MissionRecord]:
        return [m for m in self._missions.values() if m.case_id == case_id]

    def list_active(self) -> List[MissionRecord]:
        terminal = {MissionState.COMPLETE, MissionState.CLOSED}
        return [m for m in self._missions.values() if m.state not in terminal]
