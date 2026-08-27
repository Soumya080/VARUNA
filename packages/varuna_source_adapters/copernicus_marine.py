from typing import Any

class CopernicusMarineAdapter:
    def fetch_currents(self, region: Any) -> Any:
        return {"region": region, "data": "mock_cmems_data"}
