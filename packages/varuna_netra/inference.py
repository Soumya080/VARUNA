from typing import List, Any, Optional
import uuid
import numpy as np
from varuna_contracts.schemas import SlickDetection, BBox, SlickClass
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_netra.protocol import NetraProvider
from varuna_infra.model_loader import ModelLoader
from varuna_netra.ood import OODDetector
from varuna_netra.preprocessing import normalize_sar_tile, load_vv_vh_arrays
from varuna_data_eng.schemas.normalization import NormalizationRecord

from datetime import datetime, timezone

class NetraInferenceService(NetraProvider):
    def __init__(
        self,
        model_loader: ModelLoader,
        model_version: str,
        normalization_record: Optional[NormalizationRecord] = None,
    ):
        self.model_loader = model_loader
        self.model_version = model_version
        # Will raise UnregisteredModelError if not approved
        self.model = self.model_loader.load("netra", self.model_version)
        self.ood_detector = OODDetector()
        # Frozen train-split statistics from the M6 data pipeline. When set,
        # detect() normalizes the raw scene through the SAME shared function
        # NETRA's dataset/training path uses — it never recomputes per-tile
        # statistics itself.
        self.normalization_record = normalization_record
        self.last_normalized_input: Optional[np.ndarray] = None

    def detect(self, scene_path: str, wind_path: str, envelope: EvidenceEnvelope) -> List[SlickDetection]:
        # OOD check on inference
        ood_score = self.ood_detector.compute_score(logits=None)

        # Architecturally-real preprocessing path: if a frozen
        # NormalizationRecord is configured and raw VV/VH arrays are
        # available for this scene, run them through the same
        # normalize_sar_tile() the data-engineering pipeline uses. The
        # underlying detector below is still a mock — only the
        # preprocessing/normalization wiring is asserted as real here.
        self.last_normalized_input = None
        if self.normalization_record is not None:
            arrays = load_vv_vh_arrays(scene_path)
            if arrays is not None:
                vv, vh = arrays
                self.last_normalized_input = normalize_sar_tile(vv, vh, self.normalization_record)

        # Create a mock detection
        detection = SlickDetection(
            slick_id=str(uuid.uuid4()),
            scene_id="scene1",
            observation_time=datetime.now(timezone.utc),
            classification=SlickClass.OIL,
            confidence=0.85,
            mask_path="path/to/mask.png",
            centroid={"lon": 0.5, "lat": 0.5},
            bbox={"min_lon": 0.0, "min_lat": 0.0, "max_lon": 1.0, "max_lat": 1.0},
            area_km2=10.0,
            perimeter_km=4.0,
            elongation=1.0,
            orientation_deg=0.0,
            age_prior_mean_hours=12.0,
            age_prior_std_hours=2.0,
            netra_model_version=self.model_version
        )
        return [detection]

    def get_model_version(self) -> str:
        return self.model_version
