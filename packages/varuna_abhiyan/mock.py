from typing import List
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import AssetTasking, AssetType, SearchBox
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_abhiyan.protocol import AbhiyanProvider

class MockAbhiyanProvider(AbhiyanProvider):
    MOCK_VERSION = "mock-v1"

    def generate_tasking(self, search_boxes: List[SearchBox], available_assets: List[AssetType],
                         envelope: EvidenceEnvelope) -> List[AssetTasking]:
        
        # M4 rule: Must return empty if no boxes or no assets
        if not search_boxes or not available_assets:
            return []
            
        taskings = []
        launch_time = datetime.now(timezone.utc) + timedelta(minutes=30)
        
        # Greedy assignment mock
        # For simplicity, just assign the first asset to the first box
        if available_assets and search_boxes:
            taskings.append(AssetTasking(
                asset_type=available_assets[0],
                base_name="Port Blair" if search_boxes[0].center.lat < 15 else "Mumbai",
                search_box=search_boxes[0],
                pattern="expanding_square",
                launch_time=launch_time,
                flight_hours=4.0,
                probability_of_detection=0.85,
                rationale="Greedy assignment based on proximity"
            ))
            
        return taskings

    def get_model_version(self) -> str:
        return self.MOCK_VERSION
