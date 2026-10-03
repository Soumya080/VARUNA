"""Phase 7 tests: NYAYA handoff bridge. Confirms CHHAYA does not silently
become an attribution engine — the bridge only ever returns a bounded prior
nudge, never a posterior/decision."""
from varuna_chhaya.v2.contracts import ScoreType
from varuna_chhaya.v2.nyaya_handoff import CandidateEvidenceRecord, ChhayaEvidenceHandoff
from varuna_chhaya.v2.outcomes import ChhayaOutcome
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_nyaya.chhaya_bridge import DARK_CONTACT_PRIOR_WEIGHT, dark_contact_prior_contribution


def _envelope():
    return EvidenceEnvelope(artifact_id="e", produced_by="chhaya_v2",
                             provenance=Provenance(source_id="chhaya_v2"), mode=EvidenceMode.REAL)


def _handoff(outcome, candidates=None):
    return ChhayaEvidenceHandoff(
        case_id="case-1", scene_id="scene-1", outcome=outcome, outcome_reason="test",
        detector_source="cfar_ca_v1", detector_mode="classical", detector_available=True,
        coverage_quality=0.8, candidates=candidates or [], envelope=_envelope(),
    )


def _record(cid, rank, plausibility):
    return CandidateEvidenceRecord(
        candidate_id=cid, sar_vessel_score=8.0, sar_score_type=ScoreType.RELATIVE_PLAUSIBILITY.value,
        ais_state="no_ais_match", ais_distance_km=None,
        origin_spatial_consistency=0.5, origin_temporal_consistency=0.8,
        course_consistency=None, speed_consistency=None,
        relative_plausibility=plausibility, rank=rank, missing_evidence=[],
    )


def test_non_dark_vessel_outcome_gives_zero_nudge():
    handoff = _handoff(ChhayaOutcome.KNOWN_VESSEL, [_record("c1", 1, 0.9)])
    result = dark_contact_prior_contribution(handoff)
    assert result.supported is False
    assert result.prior_nudge == 0.0


def test_possible_dark_vessel_gives_bounded_positive_nudge():
    handoff = _handoff(ChhayaOutcome.POSSIBLE_DARK_VESSEL, [_record("c1", 1, 0.8)])
    result = dark_contact_prior_contribution(handoff)
    assert result.supported is True
    assert 0.0 < result.prior_nudge <= DARK_CONTACT_PRIOR_WEIGHT


def test_nudge_never_exceeds_documented_weight_even_at_max_plausibility():
    handoff = _handoff(ChhayaOutcome.POSSIBLE_DARK_VESSEL, [_record("c1", 1, 1.0)])
    result = dark_contact_prior_contribution(handoff)
    assert result.prior_nudge == DARK_CONTACT_PRIOR_WEIGHT


def test_bridge_never_returns_a_posterior_or_decision_field():
    handoff = _handoff(ChhayaOutcome.POSSIBLE_DARK_VESSEL, [_record("c1", 1, 0.7)])
    result = dark_contact_prior_contribution(handoff)
    field_names = set(vars(result).keys())
    assert "posterior" not in field_names
    assert "decision_state" not in field_names
    assert "attribution" not in field_names


def test_empty_candidates_gives_zero_nudge_even_if_outcome_mismarked():
    handoff = _handoff(ChhayaOutcome.POSSIBLE_DARK_VESSEL, [])
    result = dark_contact_prior_contribution(handoff)
    assert result.supported is False
    assert result.prior_nudge == 0.0
