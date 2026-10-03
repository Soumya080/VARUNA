import uuid
from datetime import datetime, timezone
from typing import List
from varuna_contracts.schemas import BBox, GeoPoint, EvidenceManifest
from varuna_smriti.protocol import SmritiProvider, HistoricalCase, RecurrenceCorridor, TrainingProposal

class MockSmritiProvider(SmritiProvider):
    def __init__(self):
        self._history: List[HistoricalCase] = []
        self._proposals: List[TrainingProposal] = []

    def record_outcome(self, case_id: str, outcome: dict, manifest: EvidenceManifest) -> None:
        self._history.append(HistoricalCase(
            case_id=case_id,
            slick_centroid=GeoPoint(lon=outcome.get("lon", 0.0), lat=outcome.get("lat", 0.0)),
            outcome=outcome.get("decision_state", "unknown"),
            decision_state=outcome.get("decision_state", "unknown"),
            timestamp=datetime.now(timezone.utc),
        ))

    def query_history(self, region: BBox, time_start: datetime, time_end: datetime) -> List[HistoricalCase]:
        # Helper: check if a GeoPoint is inside a BBox manually
        def _contains(bbox: BBox, point: GeoPoint) -> bool:
            return (bbox.min_lon <= point.lon <= bbox.max_lon) and \
                   (bbox.min_lat <= point.lat <= bbox.max_lat)

        return [h for h in self._history
                if _contains(region, h.slick_centroid)
                and time_start <= h.timestamp <= time_end]

    def detect_corridors(self, region: BBox) -> List[RecurrenceCorridor]:
        return []

    def propose_training_batch(self) -> TrainingProposal:
        """Returns a PENDING proposal. Never auto-approved. Threat G-07."""
        proposal = TrainingProposal(
            proposal_id=f"TP-{uuid.uuid4().hex[:8]}",
            case_ids=[h.case_id for h in self._history[-50:]],
            status="pending",  # NEVER "approved" by default
        )
        self._proposals.append(proposal)
        return proposal
