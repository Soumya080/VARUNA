"""
Real AIS SourceAdapter -- canonical import path.

The implementation lives in `varuna_integration.ais_source.EventAISAdapter`
(built by the Track-4/dataset track for the real MC20 AIS join; kept there
rather than moved here to respect a hard no-move constraint on that
session). This module re-exports it under the package a reader would
actually look in first -- `varuna_source_adapters` is the adapter package,
`varuna_integration` is the pipeline package that happened to need it
first.

    REAL AIS SOURCE -> AIS SourceAdapter -> FetchResult -> fetch_with_mode()
    -> EvidenceMode.REAL -> canonical VesselTrack -> existing NYAYA join

See `varuna_integration.ais_source` for the full adapter (fetch/health_check/
source_id, `AISJoinStatus` semantics, `stream_tracks`/`to_vessel_track`
bronze-to-canonical mapping, and `load_event_tracks` -- the Phase-3 entry
point that goes through `fetch_with_mode()` so provenance is decided by the
adapter's behaviour, never by a caller's expectation).
"""
from __future__ import annotations

from varuna_integration.ais_source import (
    AISJoinStatus,
    AISTrackJoin,
    EventAISAdapter,
    EventAISJoin,
    load_event_tracks,
    stream_tracks,
    to_vessel_track,
)

__all__ = [
    "AISJoinStatus",
    "AISTrackJoin",
    "EventAISAdapter",
    "EventAISJoin",
    "load_event_tracks",
    "stream_tracks",
    "to_vessel_track",
    "AISAdapter",
]


class AISAdapter:
    """Superseded by `EventAISAdapter` (real, `SourceAdapter`-conformant,
    reads the actual MC20 AIS join). This stub predates real AIS
    integration, has zero call sites in the codebase (verified before
    superseding it), and is left in place rather than deleted only because
    this module operates under a no-delete constraint -- do not add new
    call sites against it; use `EventAISAdapter` instead."""

    def fetch_vessels(self, region):
        return {"region": region, "vessels": []}
