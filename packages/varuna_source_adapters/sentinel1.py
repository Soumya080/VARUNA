from typing import Any

class Sentinel1Adapter:
    def fetch_scene(self, scene_id: str) -> Any:
        return {"id": scene_id, "data": "mock_s1_data"}
