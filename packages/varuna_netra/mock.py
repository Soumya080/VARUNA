import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from varuna_contracts.schemas import SlickDetection, SlickClass, GeoPoint, BBox
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_netra.protocol import NetraProvider
from varuna_netra.preprocessing import extract_wind_speed

class MockNetraProvider(NetraProvider):
    """Deterministic, seeded. Returns synthetic SlickDetections."""

    MOCK_VERSION = "mock-v1"

    def __init__(self, seed: int = 42, n_detections: int = 1):
        self._seed = seed
        self._n = n_detections

    def detect(self, scene_path: str, wind_path: Optional[str],
               envelope: EvidenceEnvelope) -> List[SlickDetection]:
        rng = np.random.default_rng(self._seed)
        wind_speed = extract_wind_speed(wind_path)
        obs_time = datetime.now(timezone.utc)
        detections = []

        for i in range(self._n):
            slick_id = f"slick-mock-{self._seed}-{i:03d}"
            cx = float(rng.uniform(70, 85))    # Indian Ocean lon
            cy = float(rng.uniform(8, 22))     # Indian Ocean lat
            half = 0.05

            confidence = 0.82 if (wind_speed is None or wind_speed >= 3.0) else 0.35
            classification = SlickClass.OIL if confidence > 0.5 else SlickClass.AMBIGUOUS

            detections.append(SlickDetection(
                slick_id=slick_id,
                scene_id=f"scene-{Path(scene_path).stem}",
                observation_time=obs_time,
                classification=classification,
                confidence=confidence,
                mask_path=f"mock/masks/{slick_id}.tif",
                centroid=GeoPoint(lon=cx, lat=cy),
                bbox=BBox(min_lon=cx-half, min_lat=cy-half,
                          max_lon=cx+half, max_lat=cy+half),
                area_km2=float(rng.uniform(0.5, 15.0)),
                perimeter_km=float(rng.uniform(3.0, 30.0)),
                elongation=float(rng.uniform(1.5, 8.0)),
                orientation_deg=float(rng.uniform(-90, 90)),
                age_prior_mean_hours=24.0,
                age_prior_std_hours=12.0,
                mean_wind_speed_ms=wind_speed,
                netra_model_version=self.MOCK_VERSION,
            ))
        return detections

    def get_model_version(self) -> str:
        return self.MOCK_VERSION
