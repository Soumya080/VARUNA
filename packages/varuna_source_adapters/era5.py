from typing import Any

class ERA5Adapter:
    def fetch_wind(self, region: Any) -> Any:
        return {"region": region, "data": "mock_era5_data"}
