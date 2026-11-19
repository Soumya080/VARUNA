from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Tuple, List

from enum import StrEnum

from varuna_contracts.schemas import AISPoint, BBox, DarkVesselDetection
from varuna_contracts.evidence import EvidenceEnvelope

class LatentFinding(StrEnum):
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    RADAR_CONTACT_WITHOUT_AIS = "radar_contact_without_ais"
    VISIBLE_SOURCES_EXIST_BUT_WEAK = "visible_sources_exist_but_weak"

class ChhayaProvider(ABC):
    @abstractmethod
    def investigate(self, scene_path: str, ais_positions: List[AISPoint],
                    scene_bbox: BBox, envelope: EvidenceEnvelope
                    ) -> Tuple[List[DarkVesselDetection], LatentFinding]:
        """Match radar contacts against AIS data."""
        pass

    @abstractmethod
    def get_model_version(self) -> str:
        pass
