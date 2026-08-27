from typing import List, Tuple, Optional
from varuna_contracts.schemas import AssetTasking, AssetType, SearchBox
from varuna_contracts.evidence import EvidenceEnvelope, ValidityState
from varuna_abhiyan.protocol import AbhiyanProvider

class AbhiyanService:
    def __init__(self, provider: AbhiyanProvider):
        self._provider = provider

    def plan_mission(self, search_boxes: List[SearchBox], available_assets: List[AssetType],
                     gate_state: Optional[ValidityState], parent_envelope: EvidenceEnvelope,
                     case_id: str) -> Tuple[List[AssetTasking], EvidenceEnvelope]:
        
        # Threat M-01: Must block planning if validity gate restricts action
        if gate_state is None or not gate_state.allows_operational_action:
            # We don't plan if it's restricted or inconclusive
            out_env = parent_envelope.derive(
                artifact_id=f"abhiyan-{case_id}",
                produced_by="abhiyan",
                model_version=self._provider.get_model_version(),
            )
            return [], out_env
            
        taskings = self._provider.generate_tasking(search_boxes, available_assets, parent_envelope)
        
        out_env = parent_envelope.derive(
            artifact_id=f"abhiyan-{case_id}",
            produced_by="abhiyan",
            model_version=self._provider.get_model_version(),
        )
        return taskings, out_env
