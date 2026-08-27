from typing import List, Dict, Any
from varuna_contracts.schemas import AssetTasking, AssetType, SearchBox
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_abhiyan.protocol import AbhiyanProvider
from varuna_abhiyan.feasibility import is_feasible
import uuid
from datetime import datetime, timezone

class TaskingOptimizer(AbhiyanProvider):
    def generate_tasking(self, search_boxes: List[SearchBox], available_assets: List[AssetType], envelope: EvidenceEnvelope) -> List[AssetTasking]:
        if not search_boxes or not available_assets:
            return []
            
        taskings = []
        for i, box in enumerate(search_boxes):
            if i < len(available_assets):
                asset = available_assets[i]
                if is_feasible(asset, box):
                    tasking = AssetTasking(
                        asset_type=asset,
                        base_name="Port Base",
                        search_box=box,
                        pattern="ladder",
                        launch_time=datetime.now(timezone.utc),
                        flight_hours=4.0,
                        probability_of_detection=0.85,
                        rationale="M5 test tasking"
                    )
                    taskings.append(tasking)
        return taskings
        
    def get_model_version(self) -> str:
        return "optimizer_v1"
