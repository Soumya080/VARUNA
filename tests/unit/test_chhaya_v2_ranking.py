"""Phase 6 tests: deterministic ranking, RELATIVE_PLAUSIBILITY not calibrated
probability, tie-breaking determinism."""
from datetime import datetime, timezone

from varuna_chhaya.v2.contracts import ScoreType, VesselCandidate
from varuna_chhaya.v2.origin_consistency import OriginConsistency
from varuna_chhaya.v2.ranking import rank_candidates
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.schemas import GeoPoint

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _envelope():
    return EvidenceEnvelope(artifact_id="e", produced_by="t", provenance=Provenance(source_id="t"), mode=EvidenceMode.REAL)


def _cand(cid, score, valid=True):
    return VesselCandidate(
        candidate_id=cid, case_id="c", scene_id="s",
        position=GeoPoint(lon=70.5, lat=10.5) if valid else None,
        geolocation_valid=valid, pixel_row=1.0, pixel_col=1.0,
        detector_source="cfar_ca_v1", detector_mode="classical",
        vessel_score=score, score_type=ScoreType.RELATIVE_PLAUSIBILITY,
        source_artifact_id="a", acquisition_time=T0, envelope=_envelope(),
    )


def test_higher_detector_score_ranks_first():
    cands = [_cand("low", 6.0), _cand("high", 12.0)]
    entries = rank_candidates(cands, {})
    assert entries[0].candidate_id == "high"
    assert entries[0].rank == 1
    assert entries[1].rank == 2


def test_score_type_is_always_relative_plausibility_never_calibrated():
    entries = rank_candidates([_cand("a", 8.0)], {})
    # ranking module never emits a "calibrated_probability" label anywhere
    assert all("calibrated" not in e.explanation.lower() or "not" in e.explanation.lower() for e in entries)


def test_invalid_geolocation_candidate_scores_zero():
    cands = [_cand("valid", 8.0), _cand("invalid", 20.0, valid=False)]
    entries = rank_candidates(cands, {})
    invalid_entry = next(e for e in entries if e.candidate_id == "invalid")
    assert invalid_entry.relative_plausibility == 0.0


def test_ranking_is_deterministic_across_repeated_calls():
    cands = [_cand("a", 7.0), _cand("b", 7.0), _cand("c", 9.0)]
    r1 = rank_candidates(cands, {})
    r2 = rank_candidates(cands, {})
    assert [e.candidate_id for e in r1] == [e.candidate_id for e in r2]


def test_ties_break_on_candidate_id_lexicographically():
    cands = [_cand("zeta", 5.0), _cand("alpha", 5.0)]
    entries = rank_candidates(cands, {})
    assert entries[0].candidate_id == "alpha"


def test_origin_bonus_shifts_ranking_when_detector_scores_tie():
    cands = [_cand("far", 5.0), _cand("near", 5.0)]
    origin = {
        "far": OriginConsistency(candidate_id="far", spatial_consistency=-0.5, temporal_consistency=0.5),
        "near": OriginConsistency(candidate_id="near", spatial_consistency=0.9, temporal_consistency=0.9),
    }
    entries = rank_candidates(cands, origin)
    assert entries[0].candidate_id == "near"


def test_missing_origin_consistency_is_recorded_not_silently_dropped():
    entries = rank_candidates([_cand("a", 8.0)], {})
    assert "origin_consistency_not_evaluated" in entries[0].missing_evidence


def test_empty_candidate_list_returns_empty():
    assert rank_candidates([], {}) == []
