from typing import Tuple, Optional

from varuna_contracts.schemas import SlickDetection, ForwardForecast
from varuna_contracts.evidence import EvidenceEnvelope, UncertaintyBlock
from varuna_pravaah.protocol import PravaahProvider

class PravaahService:
    def __init__(self, provider: PravaahProvider):
        self._provider = provider

    def forecast(self, slick: SlickDetection, forcing_path: Optional[str],
                 horizon_hours: float, parent_envelope: EvidenceEnvelope,
                 case_id: str) -> Tuple[ForwardForecast, EvidenceEnvelope]:
        forecast = self._provider.forecast_drift(
            slick, forcing_path, horizon_hours, parent_envelope
        )
        env = parent_envelope.derive(
            artifact_id=f"pravaah-{case_id}",
            produced_by="pravaah",
            model_version=self._provider.get_model_version(),
            uncertainty=UncertaintyBlock(representation="samples", n_samples=50),
        )
        return forecast, env
