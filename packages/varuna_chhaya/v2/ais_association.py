"""Phase 4 — AIS association.

Produces one of four EXPLICIT states per candidate. Critically:
"no AIS position found nearby" is NEVER, by itself, treated as "dark vessel"
— that determination additionally requires an adequate coverage assessment
and is made later, in `outcomes.py`, using this module's
`INCONCLUSIVE_AIS_COVERAGE` output as one of its required conditions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from varuna_chhaya.coverage import compute_ais_coverage, haversine_km
from varuna_chhaya.v2.contracts import VesselCandidate
from varuna_contracts.schemas import AISPoint, BBox

MATCH_RADIUS_KM = 2.0
POSSIBLE_MATCH_RADIUS_KM = 6.0
MAX_TIME_SKEW = timedelta(minutes=30)
COVERAGE_SUFFICIENT_THRESHOLD = 0.6  # same convention as v1 MockChhayaProvider


class AISAssociationState(StrEnum):
    MATCHED_AIS = "matched_ais"
    POSSIBLE_AIS_MATCH = "possible_ais_match"
    NO_AIS_MATCH = "no_ais_match"
    INCONCLUSIVE_AIS_COVERAGE = "inconclusive_ais_coverage"


@dataclass
class AISAssociationResult:
    candidate_id: str
    state: AISAssociationState
    matched_ais_point: AISPoint | None
    distance_km: float | None
    time_skew_seconds: float | None
    coverage_fraction: float
    explanation: str


def associate_candidate_with_ais(
    candidate: VesselCandidate,
    ais_positions: list[AISPoint],
    scene_bbox: BBox,
) -> AISAssociationResult:
    coverage = compute_ais_coverage(ais_positions, scene_bbox)

    if not candidate.geolocation_valid or candidate.position is None:
        return AISAssociationResult(
            candidate.candidate_id, AISAssociationState.INCONCLUSIVE_AIS_COVERAGE,
            None, None, None, coverage,
            "candidate has no valid geolocation — AIS distance cannot be computed",
        )

    if coverage < COVERAGE_SUFFICIENT_THRESHOLD:
        return AISAssociationResult(
            candidate.candidate_id, AISAssociationState.INCONCLUSIVE_AIS_COVERAGE,
            None, None, None, coverage,
            f"AIS coverage {coverage:.2f} below sufficiency threshold "
            f"{COVERAGE_SUFFICIENT_THRESHOLD} — absence of a match cannot be trusted",
        )

    best: tuple[AISPoint, float, float] | None = None
    for p in ais_positions:
        dist_km = haversine_km(candidate.position.lon, candidate.position.lat, p.lon, p.lat)
        skew_s = abs((p.timestamp - candidate.acquisition_time).total_seconds())
        if skew_s > MAX_TIME_SKEW.total_seconds():
            continue
        if best is None or dist_km < best[1]:
            best = (p, dist_km, skew_s)

    if best is None:
        return AISAssociationResult(
            candidate.candidate_id, AISAssociationState.NO_AIS_MATCH,
            None, None, None, coverage,
            f"AIS coverage sufficient ({coverage:.2f}) and no AIS position within "
            f"{MAX_TIME_SKEW} of acquisition time was found near the candidate",
        )

    p, dist_km, skew_s = best
    if dist_km <= MATCH_RADIUS_KM:
        state = AISAssociationState.MATCHED_AIS
        explanation = f"AIS position within {MATCH_RADIUS_KM}km ({dist_km:.2f}km) and {int(skew_s)}s of acquisition"
    elif dist_km <= POSSIBLE_MATCH_RADIUS_KM:
        state = AISAssociationState.POSSIBLE_AIS_MATCH
        explanation = f"AIS position within {POSSIBLE_MATCH_RADIUS_KM}km ({dist_km:.2f}km) but beyond confident match radius"
    else:
        state = AISAssociationState.NO_AIS_MATCH
        explanation = f"nearest time-consistent AIS position is {dist_km:.2f}km away, beyond {POSSIBLE_MATCH_RADIUS_KM}km"

    return AISAssociationResult(candidate.candidate_id, state, p, dist_km, skew_s, coverage, explanation)
