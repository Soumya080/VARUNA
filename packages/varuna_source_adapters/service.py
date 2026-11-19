from typing import Dict

from varuna_source_adapters.protocol import SourceAdapter, SourceQuery, FetchResult
from varuna_source_adapters.mock_cmems import MockCmemsAdapter
from varuna_source_adapters.mock_era5 import MockEra5Adapter
from varuna_source_adapters.mock_ais import MockAisAdapter
from varuna_source_adapters.mock_sentinel import MockSentinelAdapter

class AdapterRegistry:
    """Maps product_id -> adapter. Handles fallback chain."""

    def __init__(self, adapters: Dict[str, SourceAdapter]):
        self._adapters = adapters

    @classmethod
    def create_mock(cls) -> "AdapterRegistry":
        return cls(adapters={
            "cmems_current": MockCmemsAdapter(),
            "era5_wind": MockEra5Adapter(),
            "ais_tracks": MockAisAdapter(),
            "sentinel_scene": MockSentinelAdapter(),
        })

    def fetch(self, product_id: str, query: SourceQuery) -> FetchResult:
        adapter = self._adapters.get(product_id)
        if adapter is None:
            raise ValueError(f"No adapter registered for product_id={product_id}")
        return adapter.fetch(query)

    def list_adapters(self) -> Dict[str, str]:
        """Return {product_id: source_id} map for readiness endpoint."""
        return {pid: a.source_id for pid, a in self._adapters.items()}

    def health(self) -> Dict[str, bool]:
        return {pid: a.health_check() for pid, a in self._adapters.items()}
