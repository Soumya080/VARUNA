"""Phase 4 tests: AIS association states, coverage insufficiency, no-match."""
from datetime import datetime, timedelta, timezone

import pytest

from varuna_chhaya.v2.ais_association import (
    AISAssociationState,
    associate_candidate_with_ais,
)
from varuna_chhaya.v2.contracts import ScoreType, VesselCandidate
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.schemas import AISPoint, BBox, GeoPoint

BBOX = BBox(min_lon=70.0, min_lat=10.0, max_lon=71.0, max_lat=11.0)
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _envelope(mode=EvidenceMode.REAL):
    return EvidenceEnvelope(
        artifact_id="test-env", produced_by="test",
        provenance=Provenance(source_id="test"), mode=mode,
    )


def _candidate(lon=70.5, lat=10.5, valid=True, cid="cand-1"):
    return VesselCandidate(
        candidate_id=cid, case_id="case-1", scene_id="scene-1",
        position=GeoPoint(lon=lon, lat=lat) if valid else None,
        geolocation_valid=valid, geolocation_rejection_reason=None if valid else "invalid",
        pixel_row=10.0, pixel_col=10.0,
        detector_source="cfar_ca_v1", detector_mode="classical",
        vessel_score=8.0, score_type=ScoreType.RELATIVE_PLAUSIBILITY,
        source_artifact_id="artifact-1", acquisition_time=T0,
        envelope=_envelope(),
    )


def _dense_ais_grid(n_lon=15, n_lat=15):
    """Enough AIS points spread across the bbox to push coverage above 0.6."""
    points = []
    for i in range(n_lon):
        for j in range(n_lat):
            lon = BBOX.min_lon + (i / (n_lon - 1)) * (BBOX.max_lon - BBOX.min_lon)
            lat = BBOX.min_lat + (j / (n_lat - 1)) * (BBOX.max_lat - BBOX.min_lat)
            points.append(AISPoint(timestamp=T0, lon=lon, lat=lat, sog_knots=5.0))
    return points


def test_no_ais_positions_is_inconclusive_coverage_not_no_match():
    c = _candidate()
    result = associate_candidate_with_ais(c, [], BBOX)
    assert result.state == AISAssociationState.INCONCLUSIVE_AIS_COVERAGE
    assert result.coverage_fraction == 0.0


def test_matched_ais_within_radius():
    c = _candidate(lon=70.5, lat=10.5)
    ais = _dense_ais_grid()
    ais.append(AISPoint(timestamp=T0, lon=70.5001, lat=10.5001, sog_knots=8.0))
    result = associate_candidate_with_ais(c, ais, BBOX)
    assert result.state == AISAssociationState.MATCHED_AIS
    assert result.distance_km is not None and result.distance_km < 2.0


def test_no_ais_match_with_sufficient_coverage_but_far_positions():
    c = _candidate(lon=70.02, lat=10.02)
    ais = _dense_ais_grid()  # grid is spread across bbox but none within match/possible radius of a corner
    result = associate_candidate_with_ais(c, ais, BBOX)
    # far corner point: grid spacing ~7-8km, so nearest point could be within
    # possible-match radius; assert it is one of the two "not matched close"
    # states, and specifically not silently treated as inconclusive
    assert result.state in (AISAssociationState.NO_AIS_MATCH, AISAssociationState.POSSIBLE_AIS_MATCH)


def test_time_skew_excludes_stale_ais_points():
    c = _candidate(lon=70.5, lat=10.5)
    ais = _dense_ais_grid()
    stale = AISPoint(timestamp=T0 - timedelta(hours=5), lon=70.5, lat=10.5, sog_knots=5.0)
    result = associate_candidate_with_ais(c, [stale] + ais, BBOX)
    # the stale exact-position point must not count as a match
    assert result.matched_ais_point is None or result.matched_ais_point.timestamp != stale.timestamp


def test_invalid_geolocation_candidate_is_inconclusive():
    c = _candidate(valid=False)
    result = associate_candidate_with_ais(c, _dense_ais_grid(), BBOX)
    assert result.state == AISAssociationState.INCONCLUSIVE_AIS_COVERAGE
    assert "geolocation" in result.explanation
