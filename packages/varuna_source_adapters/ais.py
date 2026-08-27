from typing import Any

class AISAdapter:
    def fetch_vessels(self, region: Any) -> Any:
        return {"region": region, "vessels": []}
