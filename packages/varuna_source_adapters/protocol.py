from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from varuna_contracts.schemas import BBox
from varuna_contracts.evidence import Provenance

@dataclass(frozen=True)
class SourceQuery:
    """What to fetch. Immutable."""
    bbox: BBox
    time_start: datetime
    time_end: datetime
    product_id: str
    cache_policy: str = "cache_first"  # "cache_first" | "force_live" | "cache_only"

@dataclass
class FetchResult:
    """What came back."""
    artifact_path: str          # local file path or object-store key
    provenance: Provenance
    is_simulated: bool
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class SourceAdapter(ABC):
    """One external data source. The ONLY place httpx/cdsapi/copernicusmarine lives."""

    @abstractmethod
    def fetch(self, query: SourceQuery) -> FetchResult:
        """Fetch data for the given query. Must handle cache/fallback internally."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the source is reachable."""
        pass

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique source identifier, e.g. 'cmems.glorys12v1'."""
        pass
