"""
VARUNA GRID — AIS <-> SAR case temporal/spatial join.

Answers: "which AIS tracks could plausibly relate to this SAR case?"

Read-only, reuses varuna_chhaya.coverage.haversine_km rather than
reimplementing distance math. Does not modify any AIS track or SAR case.

Two honesty rules enforced structurally:

1. If the case has no reliable observation timestamp (Zenodo Part I has
   none — the adapter substitutes a dummy 2000-01-01 date and flags
   `timestamp_status: "unavailable"`), this module NEVER treats that dummy
   timestamp as real. Callers must pass `obs_time=None` explicitly when the
   source timestamp is unavailable, and the result's
   `temporal_join_status` becomes "unavailable" — candidates are then
   spatial-only, and every one of them carries that in its own
   `AISJoinCandidate.temporal_join_status` too, so a caller cannot lose the
   caveat by discarding the top-level result.

2. Candidates are ranked/returned with distance_km and (when temporal
   join is possible) minutes_from_obs, so downstream (NYAYA) can weigh
   them rather than receive an unweighted list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from varuna_chhaya.coverage import haversine_km
from varuna_contracts.schemas import BBox, VesselTrack

TemporalJoinStatus = Literal["joined", "unavailable"]


@dataclass(frozen=True)
class AISJoinCandidate:
    """One candidate vessel track for a case, with the provenance of why it
    was included."""
    mmsi: str
    track: VesselTrack
    distance_km: float
    minutes_from_obs: float | None  # None when temporal_join_status is "unavailable"
    temporal_join_status: TemporalJoinStatus


@dataclass(frozen=True)
class AISJoinResult:
    case_bbox: BBox
    obs_time: datetime | None
    temporal_join_status: TemporalJoinStatus
    search_radius_km: float
    window_before_hours: float
    window_after_hours: float
    candidates: list[AISJoinCandidate] = field(default_factory=list)
    provenance_note: str = ""


def _bbox_center(bbox: BBox) -> tuple[float, float]:
    return (
        (bbox.min_lon + bbox.max_lon) / 2.0,
        (bbox.min_lat + bbox.max_lat) / 2.0,
    )


def _track_min_distance_to_point(track: VesselTrack, lon: float, lat: float) -> float:
    """Closest approach of any point in the track to (lon, lat), in km."""
    if not track.points:
        return float("inf")
    return min(haversine_km(p.lon, p.lat, lon, lat) for p in track.points)


def _track_points_within_window(
    track: VesselTrack, obs_time: datetime, before: timedelta, after: timedelta
) -> list:
    lo, hi = obs_time - before, obs_time + after
    return [p for p in track.points if lo <= p.timestamp <= hi]


def find_candidate_tracks(
    case_bbox: BBox,
    obs_time: datetime | None,
    tracks: list[VesselTrack],
    *,
    search_radius_km: float = 50.0,
    window_before_hours: float = 48.0,
    window_after_hours: float = 6.0,
) -> AISJoinResult:
    """Find AIS tracks that could plausibly relate to a SAR case.

    `obs_time=None` MUST be passed when the SAR case's acquisition timestamp
    is unavailable (never pass a substituted/dummy timestamp here) — this
    function does not guess, and its result makes that explicit via
    `temporal_join_status`.

    Window defaults (48h before / 6h after) mirror the existing
    `ais_window_before_hours` / `ais_window_after_hours` values found in
    `src/common/config.py` — not re-invented here, just not wired to a live
    config loader yet (that package is currently dead code; see the
    reconciliation report).
    """
    center_lon, center_lat = _bbox_center(case_bbox)
    temporal_status: TemporalJoinStatus = "joined" if obs_time is not None else "unavailable"

    candidates: list[AISJoinCandidate] = []
    for track in tracks:
        if temporal_status == "joined":
            windowed = _track_points_within_window(
                track, obs_time,
                timedelta(hours=window_before_hours),
                timedelta(hours=window_after_hours),
            )
            if not windowed:
                continue
            dist = min(haversine_km(p.lon, p.lat, center_lon, center_lat) for p in windowed)
            if dist > search_radius_km:
                continue
            closest = min(windowed, key=lambda p: abs((p.timestamp - obs_time).total_seconds()))
            minutes_from_obs = abs((closest.timestamp - obs_time).total_seconds()) / 60.0
        else:
            # No reliable observation time: spatial-only screening across the
            # whole track. This is deliberately permissive (any point in
            # range, any time) because we cannot narrow by time — the
            # candidate list is a superset an operator/NYAYA must weigh
            # knowing temporal_join_status="unavailable", not a precise match.
            dist = _track_min_distance_to_point(track, center_lon, center_lat)
            if dist > search_radius_km:
                continue
            minutes_from_obs = None

        candidates.append(AISJoinCandidate(
            mmsi=track.mmsi,
            track=track,
            distance_km=round(dist, 3),
            minutes_from_obs=minutes_from_obs,
            temporal_join_status=temporal_status,
        ))

    candidates.sort(key=lambda c: c.distance_km)

    return AISJoinResult(
        case_bbox=case_bbox,
        obs_time=obs_time,
        temporal_join_status=temporal_status,
        search_radius_km=search_radius_km,
        window_before_hours=window_before_hours,
        window_after_hours=window_after_hours,
        candidates=candidates,
        provenance_note=(
            "Temporal+spatial join." if temporal_status == "joined"
            else "Spatial-only screening: no reliable SAR observation timestamp "
                 "was provided. Candidates are NOT time-filtered and must be "
                 "treated as a superset, not a match."
        ),
    )
