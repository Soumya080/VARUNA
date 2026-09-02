"""CHHAYA v2 outcome states, including the dark-vessel semantics guard.

A dark-vessel result is DELIBERATELY hard to reach. Per the governing task:
"SAR detection + no AIS match = dark vessel" is invalid. `classify_outcome()`
requires ALL of:
  1. the detector was available and actually ran (not SAR_EVIDENCE_UNAVAILABLE)
  2. at least one candidate has valid geolocation (not INVALID_GEOLOCATION-only)
  3. AIS coverage was assessed as adequate for at least one such candidate
     (not INCONCLUSIVE_AIS_COVERAGE)
  4. that candidate's AIS association state is NO_AIS_MATCH specifically
     (POSSIBLE_AIS_MATCH is NOT sufficient — it is deliberately excluded)
  5. origin/corridor consistency was evaluated for that candidate (its
     presence, not any particular value, is what's required — a candidate
     with no Phi field available at all falls back to INCONCLUSIVE, since
     "relevant origin/corridor consistency where possible" was not possible)
Any missing condition falls back to INCONCLUSIVE rather than guessing.
"""
from __future__ import annotations

from enum import StrEnum

from varuna_chhaya.v2.ais_association import AISAssociationResult, AISAssociationState
from varuna_chhaya.v2.origin_consistency import OriginConsistency


class ChhayaOutcome(StrEnum):
    KNOWN_VESSEL = "known_vessel"
    POSSIBLE_DARK_VESSEL = "possible_dark_vessel"
    INCONCLUSIVE = "inconclusive"
    NO_SUPPORTED_VESSEL = "no_supported_vessel"
    INCONCLUSIVE_AIS_COVERAGE = "inconclusive_ais_coverage"
    SAR_EVIDENCE_UNAVAILABLE = "sar_evidence_unavailable"
    INVALID_GEOLOCATION = "invalid_geolocation"


def classify_outcome(
    detector_available: bool,
    n_candidates_total: int,
    n_candidates_valid_geo: int,
    ais_results: list[AISAssociationResult],
    origin_by_id: dict[str, OriginConsistency],
) -> tuple[ChhayaOutcome, str]:
    if not detector_available:
        return ChhayaOutcome.SAR_EVIDENCE_UNAVAILABLE, "detector reported unavailable — see detector_source/get_model_version()"

    if n_candidates_total == 0:
        return ChhayaOutcome.NO_SUPPORTED_VESSEL, "detector ran and found zero candidates above threshold"

    if n_candidates_valid_geo == 0:
        return ChhayaOutcome.INVALID_GEOLOCATION, "every candidate failed geolocation validation"

    if any(r.state == AISAssociationState.MATCHED_AIS for r in ais_results):
        return ChhayaOutcome.KNOWN_VESSEL, "at least one candidate matched a known AIS position"

    if all(r.state == AISAssociationState.INCONCLUSIVE_AIS_COVERAGE for r in ais_results):
        return ChhayaOutcome.INCONCLUSIVE_AIS_COVERAGE, "AIS coverage was insufficient for every candidate — absence of a match is not informative"

    dark_candidates = [
        r for r in ais_results
        if r.state == AISAssociationState.NO_AIS_MATCH
    ]
    if dark_candidates:
        # Require origin/corridor consistency to have been EVALUATED (not
        # necessarily favorable — a low or negative spatial_consistency is
        # still real evidence and is surfaced in the ranking; we only refuse
        # to call POSSIBLE_DARK_VESSEL when that evaluation never happened
        # at all, i.e. no Phi field / no valid geolocation to evaluate it).
        supported = [
            r for r in dark_candidates
            if origin_by_id.get(r.candidate_id) is not None
            and "phi_field_unavailable" not in origin_by_id[r.candidate_id].missing_evidence
            and "candidate_has_no_valid_geolocation" not in origin_by_id[r.candidate_id].missing_evidence
        ]
        if supported:
            return ChhayaOutcome.POSSIBLE_DARK_VESSEL, (
                f"{len(supported)} candidate(s) have valid SAR evidence, valid geography, "
                f"adequate AIS coverage, no supported AIS match, and an evaluated origin/"
                f"corridor consistency — meets the dark-vessel evidentiary bar"
            )
        return ChhayaOutcome.INCONCLUSIVE, (
            "candidate(s) have no AIS match and adequate coverage, but origin/corridor "
            "consistency could not be evaluated (no Phi field available) — dark-vessel "
            "semantics require it where possible, so this stays INCONCLUSIVE rather than "
            "a determination"
        )

    return ChhayaOutcome.INCONCLUSIVE, "remaining candidates are POSSIBLE_AIS_MATCH only — not strong enough for KNOWN_VESSEL or dark-vessel"
