from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from varuna_contracts.schemas import BBox, GeoPoint, EvidenceManifest

@dataclass
class HistoricalCase:
    case_id: str
    slick_centroid: GeoPoint
    outcome: str
    decision_state: str
    timestamp: datetime

@dataclass
class RecurrenceCorridor:
    corridor_id: str
    bbox: BBox
    case_count: int
    last_seen: datetime

@dataclass
class TrainingProposal:
    proposal_id: str
    case_ids: List[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: Optional[str] = None   # MUST be set before use
    status: str = "pending"          # "pending" | "approved" | "rejected"

class SmritiProvider(ABC):
    @abstractmethod
    def record_outcome(self, case_id: str, outcome: dict, manifest: EvidenceManifest) -> None:
        pass
        
    @abstractmethod
    def query_history(self, region: BBox, time_start: datetime, time_end: datetime) -> List[HistoricalCase]:
        pass

    @abstractmethod
    def detect_corridors(self, region: BBox) -> List[RecurrenceCorridor]:
        pass

    @abstractmethod
    def propose_training_batch(self) -> TrainingProposal:
        pass
