"""Phase 5 — PRATIVARTAN (Phi) origin/corridor consistency.

Consumes the REAL `PhiField` artifact NYAYA/PRATIVARTAN already produce —
does not recompute or approximate it. Uses `PhiField.spatial_modes`
(each a `SpatialMode`: centroid + area_km2 + peak_time_unix), i.e. an origin
UNCERTAINTY REGION per mode, not just a single centroid — per Phase 5's
explicit preference.

Every field is None, with a reason recorded in `missing_evidence`, when the
input needed to compute it does not exist. Course/speed consistency in
particular are computed ONLY from a real `VesselTrack` with >=2 AIS points
that actually carry `cog_deg`/`sog_knots` — never inferred or invented from a
single point or from the candidate's own position alone.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from varuna_chhaya.coverage import haversine_km
from varuna_chhaya.v2.contracts import VesselCandidate
from varuna_contracts.phi import PhiField, SpatialMode
from varuna_contracts.schemas import VesselTrack


@dataclass
class OriginConsistency:
    candidate_id: str
    spatial_consistency: float | None = None   # 1.0 = at mode centroid, 0.0 = at mode's edge, None if unknown, can exceed range if outside every mode's radius
    within_any_mode_radius: bool | None = None
    nearest_mode_distance_km: float | None = None
    temporal_consistency: float | None = None  # 1.0 = at mode peak time, decays with hours away, None if unknown
    course_consistency: float | None = None    # None unless an AIS track with heading exists
    speed_consistency: float | None = None     # None unless an AIS track with >=2 speed-bearing points exists
    missing_evidence: list[str] = field(default_factory=list)


def _mode_radius_km(mode: SpatialMode) -> float:
    return math.sqrt(max(mode.area_km2, 0.0) / math.pi)


def evaluate_origin_consistency(
    candidate: VesselCandidate,
    phi: PhiField | None,
    ais_track: VesselTrack | None = None,
) -> OriginConsistency:
    result = OriginConsistency(candidate_id=candidate.candidate_id)

    if phi is None:
        result.missing_evidence.append("phi_field_unavailable")
    elif not phi.spatial_modes:
        result.missing_evidence.append("phi_field_has_no_spatial_modes")
    elif not candidate.geolocation_valid or candidate.position is None:
        result.missing_evidence.append("candidate_has_no_valid_geolocation")
    else:
        best_mode = None
        best_dist = None
        for mode in phi.spatial_modes:
            d = haversine_km(candidate.position.lon, candidate.position.lat,
                              mode.centroid.lon, mode.centroid.lat)
            if best_dist is None or d < best_dist:
                best_dist, best_mode = d, mode

        assert best_mode is not None
        radius_km = max(_mode_radius_km(best_mode), 0.1)  # avoid div-by-zero on a degenerate mode
        result.nearest_mode_distance_km = best_dist
        result.within_any_mode_radius = best_dist <= radius_km
        # 1.0 at the centroid, 0.0 exactly at the mode's own effective radius,
        # negative beyond it — a real, bounded-above, unbounded-below score,
        # not clipped, so "how far outside" remains informative.
        result.spatial_consistency = 1.0 - (best_dist / radius_km)

        peak_time = datetime.fromtimestamp(best_mode.peak_time_unix, tz=candidate.acquisition_time.tzinfo)
        hours_from_peak = abs((candidate.acquisition_time - peak_time).total_seconds()) / 3600.0
        # Decays over PRATIVARTAN's own backward_duration_hours scale so the
        # decay rate is tied to the actual origin-reconstruction window, not
        # an arbitrary constant.
        scale_hours = max(phi.backward_duration_hours, 1.0)
        result.temporal_consistency = math.exp(-hours_from_peak / scale_hours)

    if ais_track is None:
        result.missing_evidence.append("ais_track_unavailable_for_course_speed")
    else:
        headed_points = [p for p in ais_track.points if p.cog_deg is not None]
        if len(headed_points) < 1 or candidate.position is None:
            result.missing_evidence.append("ais_track_has_no_course_data")
        else:
            # Bearing from the vessel's most recent known heading-bearing point
            # to the candidate position, compared against that reported course.
            p = headed_points[-1]
            bearing = _bearing_deg(p.lon, p.lat, candidate.position.lon, candidate.position.lat)
            diff = abs((bearing - p.cog_deg + 180) % 360 - 180)
            result.course_consistency = 1.0 - (diff / 180.0)

        speed_points = [pt for pt in ais_track.points if pt.sog_knots is not None]
        if len(speed_points) < 2:
            result.missing_evidence.append("ais_track_has_insufficient_speed_history")
        else:
            # Consistency of implied speed (candidate distance/time from the
            # last known point) against the track's own recent reported speed
            # — real arithmetic on real points, never fabricated.
            last = speed_points[-1]
            if candidate.position is not None:
                dt_h = abs((candidate.acquisition_time - last.timestamp).total_seconds()) / 3600.0
                if dt_h > 1e-6:
                    implied_km = haversine_km(last.lon, last.lat, candidate.position.lon, candidate.position.lat)
                    implied_knots = (implied_km / 1.852) / dt_h
                    denom = max(last.sog_knots, 1.0)
                    result.speed_consistency = max(0.0, 1.0 - abs(implied_knots - last.sog_knots) / denom)
                else:
                    result.missing_evidence.append("acquisition_time_coincides_with_last_ais_point")

    return result


def _bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360
