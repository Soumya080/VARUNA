from typing import Tuple, List

from varuna_contracts.schemas import AISPoint, BBox, DarkVesselDetection
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_chhaya.protocol import ChhayaProvider, LatentFinding

class ChhayaService:
    def __init__(self, provider: ChhayaProvider):
        self._provider = provider

    def investigate(self, scene_path: str, ais_positions: List[AISPoint],
                    scene_bbox: BBox, parent_envelope: EvidenceEnvelope,
                    case_id: str
                    ) -> Tuple[List[DarkVesselDetection], LatentFinding, EvidenceEnvelope]:
        detections, finding = self._provider.investigate(
            scene_path, ais_positions, scene_bbox, parent_envelope
        )
        out_env = parent_envelope.derive(
            artifact_id=f"chhaya-{case_id}",
            produced_by="chhaya",
            model_version=self._provider.get_model_version(),
        )
        return detections, finding, out_env
