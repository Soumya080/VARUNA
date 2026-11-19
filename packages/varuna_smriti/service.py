from datetime import datetime
from typing import List
from varuna_contracts.schemas import BBox, EvidenceManifest
from varuna_smriti.protocol import SmritiProvider, HistoricalCase, RecurrenceCorridor, TrainingProposal

class SmritiService:
    def __init__(self, provider: SmritiProvider):
        self._provider = provider

    def record_outcome(self, case_id: str, outcome: dict, manifest: EvidenceManifest) -> None:
        self._provider.record_outcome(case_id, outcome, manifest)

    def query_history(self, region: BBox, time_start: datetime, time_end: datetime) -> List[HistoricalCase]:
        return self._provider.query_history(region, time_start, time_end)
        
    def detect_corridors(self, region: BBox) -> List[RecurrenceCorridor]:
        return self._provider.detect_corridors(region)
        
    def propose_training_batch(self) -> TrainingProposal:
        return self._provider.propose_training_batch()
        
    def trigger_learning_loop(self) -> None:
        """Trigger the SMRITI learning loop."""
        proposal = self.propose_training_batch()
        if proposal.status == "approved":
            pass # Dispatch to task runner in real system
