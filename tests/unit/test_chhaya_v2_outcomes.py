"""Dark-vessel semantics guard tests — the most safety-critical logic in
CHHAYA v2: "SAR detection + no AIS match = dark vessel" must be REJECTED as
insufficient; the real bar requires coverage adequacy AND an evaluated
origin/corridor consistency."""
from varuna_chhaya.v2.ais_association import AISAssociationResult, AISAssociationState
from varuna_chhaya.v2.origin_consistency import OriginConsistency
from varuna_chhaya.v2.outcomes import ChhayaOutcome, classify_outcome


def _ais(cid, state):
    return AISAssociationResult(candidate_id=cid, state=state, matched_ais_point=None,
                                 distance_km=None, time_skew_seconds=None,
                                 coverage_fraction=0.8, explanation="x")


def test_detector_unavailable_short_circuits_to_sar_unavailable():
    outcome, reason = classify_outcome(False, 0, 0, [], {})
    assert outcome == ChhayaOutcome.SAR_EVIDENCE_UNAVAILABLE


def test_zero_candidates_is_no_supported_vessel():
    outcome, _ = classify_outcome(True, 0, 0, [], {})
    assert outcome == ChhayaOutcome.NO_SUPPORTED_VESSEL


def test_all_geolocation_invalid_is_invalid_geolocation():
    outcome, _ = classify_outcome(True, 3, 0, [], {})
    assert outcome == ChhayaOutcome.INVALID_GEOLOCATION


def test_matched_ais_is_known_vessel():
    ais = [_ais("c1", AISAssociationState.MATCHED_AIS)]
    outcome, _ = classify_outcome(True, 1, 1, ais, {"c1": OriginConsistency(candidate_id="c1")})
    assert outcome == ChhayaOutcome.KNOWN_VESSEL


def test_insufficient_coverage_everywhere_is_inconclusive_coverage():
    ais = [_ais("c1", AISAssociationState.INCONCLUSIVE_AIS_COVERAGE)]
    outcome, _ = classify_outcome(True, 1, 1, ais, {})
    assert outcome == ChhayaOutcome.INCONCLUSIVE_AIS_COVERAGE


def test_no_ais_match_alone_without_origin_evaluation_is_NOT_dark_vessel():
    """The critical guard: no-AIS-match by itself must not produce
    POSSIBLE_DARK_VESSEL. Origin/corridor consistency was never evaluated
    here (no Phi field), so this must fall back to INCONCLUSIVE."""
    ais = [_ais("c1", AISAssociationState.NO_AIS_MATCH)]
    origin = {"c1": OriginConsistency(candidate_id="c1", missing_evidence=["phi_field_unavailable"])}
    outcome, reason = classify_outcome(True, 1, 1, ais, origin)
    assert outcome == ChhayaOutcome.INCONCLUSIVE
    assert outcome != ChhayaOutcome.POSSIBLE_DARK_VESSEL


def test_no_ais_match_with_evaluated_origin_consistency_is_possible_dark_vessel():
    ais = [_ais("c1", AISAssociationState.NO_AIS_MATCH)]
    origin = {"c1": OriginConsistency(candidate_id="c1", spatial_consistency=0.5, temporal_consistency=0.8)}
    outcome, reason = classify_outcome(True, 1, 1, ais, origin)
    assert outcome == ChhayaOutcome.POSSIBLE_DARK_VESSEL
    assert "evaluated origin" in reason


def test_possible_ais_match_alone_is_inconclusive_not_dark_vessel():
    ais = [_ais("c1", AISAssociationState.POSSIBLE_AIS_MATCH)]
    origin = {"c1": OriginConsistency(candidate_id="c1", spatial_consistency=0.5)}
    outcome, _ = classify_outcome(True, 1, 1, ais, origin)
    assert outcome == ChhayaOutcome.INCONCLUSIVE


def test_invalid_geolocation_candidate_excluded_from_dark_vessel_support():
    ais = [_ais("c1", AISAssociationState.NO_AIS_MATCH)]
    origin = {"c1": OriginConsistency(candidate_id="c1", spatial_consistency=0.5,
                                       missing_evidence=["candidate_has_no_valid_geolocation"])}
    outcome, _ = classify_outcome(True, 1, 1, ais, origin)
    assert outcome != ChhayaOutcome.POSSIBLE_DARK_VESSEL
