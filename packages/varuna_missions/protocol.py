from abc import ABC, abstractmethod
from typing import List, Optional
from varuna_contracts.schemas import AssetTasking
from varuna_contracts.states import MissionState, MissionRecord

class MissionRuntime(ABC):
    @abstractmethod
    def create_mission(self, case_id: str, asset_id: str, tasking: AssetTasking) -> MissionRecord:
        pass
        
    @abstractmethod
    def approve_and_assign(self, mission_id: str, approved_by: str) -> MissionRecord:
        pass
        
    @abstractmethod
    def transition(self, mission_id: str, new_state: MissionState, *, reason: Optional[str] = None) -> MissionRecord:
        pass
        
    @abstractmethod
    def get(self, mission_id: str) -> Optional[MissionRecord]:
        pass
        
    @abstractmethod
    def list_by_case(self, case_id: str) -> List[MissionRecord]:
        pass
        
    @abstractmethod
    def list_active(self) -> List[MissionRecord]:
        pass
