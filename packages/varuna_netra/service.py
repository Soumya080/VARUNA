from typing import Tuple, List, Optional
from varuna_contracts.schemas import SlickDetection
from varuna_contracts.evidence import EvidenceEnvelope, AnomalyFlag, DegradationState, QualityMetrics
from varuna_netra.protocol import NetraProvider
from varuna_netra.preprocessing import extract_wind_speed

class NetraService:
    """Orchestrates preprocessing -> detection -> envelope wrapping."""

    def __init__(self, provider: NetraProvider):
        self._provider = provider

    def detect_slicks(self, scene_path: str, wind_path: Optional[str],
                      parent_envelope: EvidenceEnvelope,
                      case_id: str) -> Tuple[List[SlickDetection], EvidenceEnvelope]:
        """Full detection pipeline.

        Returns:
            (detections, output_envelope) - envelope derived from parent.
        """
        detections = self._provider.detect(scene_path, wind_path, parent_envelope)

        wind_speed = extract_wind_speed(wind_path)
        add_flags = []
        degradation = None
        if wind_speed is not None and wind_speed < 3.0:
            add_flags.append(AnomalyFlag.PHYSICALLY_IMPLAUSIBLE)  # low wind
            degradation = DegradationState.PARTIAL_INPUT_LOSS

        out_envelope = parent_envelope.derive(
            artifact_id=f"netra-{case_id}",
            produced_by="netra",
            model_version=self._provider.get_model_version(),
            quality=QualityMetrics(
                model_confidence=max((d.confidence for d in detections), default=0.0)
            ),
            add_flags=add_flags,
            degradation=degradation,
        )
        return detections, out_envelope

    def get_model_version(self) -> str:
        return self._provider.get_model_version()
