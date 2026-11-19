from abc import ABC, abstractmethod
from typing import List, Optional
from varuna_contracts.schemas import AssetTasking, AssetType, SearchBox
from varuna_contracts.evidence import EvidenceEnvelope

class AbhiyanProvider(ABC):
    @abstractmethod
    def generate_tasking(self, search_boxes: List[SearchBox], available_assets: List[AssetType],
                         envelope: EvidenceEnvelope) -> List[AssetTasking]:
        """Generate optimal mission tasking."""
        pass
    
    @abstractmethod
    def get_model_version(self) -> str:
        pass
