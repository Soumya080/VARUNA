from typing import Tuple, List
from pathlib import Path
import math

from varuna_contracts.schemas import AISPoint, BBox, DarkVesselDetection, GeoPoint
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_chhaya.protocol import ChhayaProvider, LatentFinding
from varuna_chhaya.coverage import compute_ais_coverage, haversine_km

class MockChhayaProvider(ChhayaProvider):
    MOCK_VERSION = "mock-v1"

    def investigate(self, scene_path: str, ais_positions: List[AISPoint],
                    scene_bbox: BBox, envelope: EvidenceEnvelope
                    ) -> Tuple[List[DarkVesselDetection], LatentFinding]:
        coverage = compute_ais_coverage(ais_positions, scene_bbox)

        if coverage < 0.6:
            return [], LatentFinding.INSUFFICIENT_COVERAGE

        # Check if any AIS within 10km of bbox center
        center = scene_bbox.center
        has_nearby = any(
            haversine_km(p.lon, p.lat, center.lon, center.lat) < 10.0
            for p in ais_positions
        )

        if not has_nearby:
            # Deterministic ID
            det_id = f"dark-mock-{hash(scene_path) % 10000:04d}"
            detection = DarkVesselDetection(
                detection_id=det_id,
                scene_id=Path(scene_path).stem,
                position=GeoPoint(lon=center.lon, lat=center.lat),
                confidence=0.6,
                is_dark=True,
                distance_to_slick_km=0.0,
            )
            return [detection], LatentFinding.RADAR_CONTACT_WITHOUT_AIS

        return [], LatentFinding.VISIBLE_SOURCES_EXIST_BUT_WEAK

    def get_model_version(self) -> str:
        return self.MOCK_VERSION
