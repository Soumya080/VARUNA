from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional

from varuna_contracts.schemas import SlickDetection
from varuna_contracts.evidence import EvidenceEnvelope

class NetraProvider(ABC):
    """Perception layer. Detects and classifies dark features in SAR."""

    @abstractmethod
    def detect(self, scene_path: str, wind_path: Optional[str],
               envelope: EvidenceEnvelope) -> List[SlickDetection]:
        """Run detection on a preprocessed scene.

        Args:
            scene_path: Path to VV/VH GeoTIFF (preprocessed)
            wind_path: Path to ERA5 wind .npz (optional, for low-wind flag)
            envelope: Parent envelope from data guard

        Returns:
            List of detected slicks. Empty list is valid (no detection).
        """
        pass

    @abstractmethod
    def get_model_version(self) -> str:
        """Return the version string stamped on outputs."""
        pass
