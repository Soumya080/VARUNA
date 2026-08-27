from abc import ABC, abstractmethod
from typing import Optional
from varuna_contracts.schemas import SlickDetection, ForwardForecast
from varuna_contracts.evidence import EvidenceEnvelope

class PravaahProvider(ABC):
    @abstractmethod
    def forecast_drift(self, slick: SlickDetection, forcing_path: Optional[str],
                       horizon_hours: float, envelope: EvidenceEnvelope
                       ) -> ForwardForecast:
        pass

    @abstractmethod
    def get_model_version(self) -> str:
        pass
