from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from varuna_contracts.schemas import BBox
from varuna_contracts.evidence import EvidenceMode, Provenance

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


def evidence_mode_of(result: FetchResult) -> EvidenceMode:
    """
    The ONE place `FetchResult.is_simulated` becomes an `EvidenceMode`
    (ADR-0006). Every caller that turns a `FetchResult` into an
    `EvidenceEnvelope` must go through this rather than re-deriving the
    mapping inline — that is what makes "config cannot upgrade provenance"
    checkable by a single static scan instead of one per call site.

        is_simulated=False -> EvidenceMode.REAL
        is_simulated=True  -> EvidenceMode.SIMULATED

    There is no third branch here for UNAVAILABLE: a `FetchResult` only
    exists once a fetch has *succeeded* — an unavailable source doesn't
    produce one, it raises (`FileNotFoundError` in `Era5Adapter`/
    `CmemsAdapter` today) or fails `health_check()`. See `fetch_with_mode()`
    below for the wrapper that turns "adapter raised" into
    `EvidenceMode.UNAVAILABLE` rather than letting every call site
    reimplement that translation too.
    """
    return EvidenceMode.SIMULATED if result.is_simulated else EvidenceMode.REAL


def fetch_with_mode(
    adapter: SourceAdapter, query: SourceQuery,
) -> tuple[FetchResult | None, EvidenceMode]:
    """
    Fetch through `adapter`, returning `(result, mode)` where `mode` is
    always one of REAL/SIMULATED/UNAVAILABLE — never inferred from
    environment or settings, only from what the adapter actually did:

      - adapter.health_check() is False        -> (None, UNAVAILABLE)
      - adapter.fetch(query) raises             -> (None, UNAVAILABLE)
      - adapter.fetch(query) succeeds           -> (result, evidence_mode_of(result))

    This is the reusable boundary Phase 1 asks for. It does not change
    `SourceAdapter`'s abstract contract — every existing mock keeps working
    unmodified, since this is a free function over the existing ABC, not a
    new abstract method.
    """
    if not adapter.health_check():
        return None, EvidenceMode.UNAVAILABLE
    try:
        result = adapter.fetch(query)
    except Exception:
        return None, EvidenceMode.UNAVAILABLE
    return result, evidence_mode_of(result)
