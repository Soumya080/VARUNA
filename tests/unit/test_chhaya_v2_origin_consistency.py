"""Phase 5 tests: PRATIVARTAN (Phi) origin/corridor consistency, and the
"never invent trajectory evidence" guard for course/speed consistency."""
from datetime import datetime, timedelta, timezone

from varuna_chhaya.v2.contracts import ScoreType, VesselCandidate
from varuna_chhaya.v2.origin_consistency import evaluate_origin_consistency
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.phi import (
    ConvergenceFlag,
    PhiDiagnostics,
    PhiField,
    SpatialMode,
    TimeDistribution,
)
from varuna_contracts.schemas import AISPoint, BBox, GeoPoint, VesselTrack, VesselType

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
BBOX = BBox(min_lon=70.0, min_lat=10.0, max_lon=71.0, max_lat=11.0)


def _envelope():
    return EvidenceEnvelope(
        artifact_id="env", produced_by="test",
        provenance=Provenance(source_id="test"), mode=EvidenceMode.REAL,
    )


def _candidate(lon, lat, cid="c1", acquisition_time=T0):
    return VesselCandidate(
        candidate_id=cid, case_id="case-1", scene_id="scene-1",
        position=GeoPoint(lon=lon, lat=lat), geolocation_valid=True,
        pixel_row=1.0, pixel_col=1.0, detector_source="cfar_ca_v1", detector_mode="classical",
        vessel_score=8.0, score_type=ScoreType.RELATIVE_PLAUSIBILITY,
        source_artifact_id="a1", acquisition_time=acquisition_time, envelope=_envelope(),
    )


def _phi_field(mode_lon=70.5, mode_lat=10.5, area_km2=25.0, peak_time=T0, backward_hours=48.0):
    mode = SpatialMode(centroid=GeoPoint(lon=mode_lon, lat=mode_lat), mass=0.9,
                        area_km2=area_km2, peak_time_unix=peak_time.timestamp())
    td = TimeDistribution(time_edges_unix=[peak_time.timestamp() - 3600, peak_time.timestamp() + 3600],
                           mass=[1.0], mode_unix=peak_time.timestamp(),
                           p05_unix=peak_time.timestamp() - 1800, p95_unix=peak_time.timestamp() + 1800)
    diag = PhiDiagnostics(entropy=0.3, concentration=0.7, effective_support_km2=100.0,
                           convergence=0.05, convergence_flag=ConvergenceFlag.CONVERGED,
                           n_modes=1, particles_seeded=1000, ensemble_members_completed=8,
                           ensemble_members_requested=8, runtime_seconds=10.0)
    return PhiField(
        phi_id="phi-1", slick_id="slick-1", case_id="case-1", data_path="x.npz",
        bbox=BBOX, grid_shape=(1, 10, 10), time_distribution=td, spatial_modes=[mode],
        diagnostics=diag, n_particles=1000, n_ensemble=8, backward_duration_hours=backward_hours,
        dt_seconds=60.0, forcing_current_source="cmems", forcing_wind_source="era5",
        envelope=_envelope(),
    )


def test_no_phi_field_gives_none_and_missing_evidence():
    c = _candidate(70.5, 10.5)
    result = evaluate_origin_consistency(c, phi=None, ais_track=None)
    assert result.spatial_consistency is None
    assert result.temporal_consistency is None
    assert "phi_field_unavailable" in result.missing_evidence


def test_candidate_at_mode_centroid_scores_near_one():
    phi = _phi_field(mode_lon=70.5, mode_lat=10.5)
    c = _candidate(70.5, 10.5)
    result = evaluate_origin_consistency(c, phi=phi, ais_track=None)
    assert result.spatial_consistency == 1.0
    assert result.within_any_mode_radius is True
    assert result.temporal_consistency > 0.99  # candidate time == peak time


def test_candidate_far_from_mode_scores_negative():
    phi = _phi_field(mode_lon=70.5, mode_lat=10.5, area_km2=1.0)  # small radius
    c = _candidate(70.9, 10.9)  # far away
    result = evaluate_origin_consistency(c, phi=phi, ais_track=None)
    assert result.spatial_consistency < 0.0
    assert result.within_any_mode_radius is False


def test_no_ais_track_leaves_course_speed_none_not_invented():
    phi = _phi_field()
    c = _candidate(70.5, 10.5)
    result = evaluate_origin_consistency(c, phi=phi, ais_track=None)
    assert result.course_consistency is None
    assert result.speed_consistency is None
    assert "ais_track_unavailable_for_course_speed" in result.missing_evidence


def test_ais_track_with_course_and_speed_yields_real_consistency_values():
    track = VesselTrack(
        mmsi="123456789", vessel_type=VesselType.UNKNOWN,
        points=[
            AISPoint(timestamp=T0 - timedelta(minutes=30), lon=70.4, lat=10.4, sog_knots=10.0, cog_deg=45.0),
            AISPoint(timestamp=T0 - timedelta(minutes=10), lon=70.45, lat=10.45, sog_knots=10.0, cog_deg=45.0),
        ],
    )
    c = _candidate(70.5, 10.5, acquisition_time=T0)
    result = evaluate_origin_consistency(c, phi=None, ais_track=track)
    assert result.course_consistency is not None
    assert result.speed_consistency is not None
    assert 0.0 <= result.course_consistency <= 1.0


def test_single_point_track_has_no_speed_history():
    track = VesselTrack(
        mmsi="123456789",
        points=[
            AISPoint(timestamp=T0, lon=70.4, lat=10.4, sog_knots=10.0, cog_deg=45.0),
            AISPoint(timestamp=T0, lon=70.401, lat=10.401, sog_knots=None, cog_deg=None),
        ],
    )
    c = _candidate(70.5, 10.5)
    result = evaluate_origin_consistency(c, phi=None, ais_track=track)
    assert result.speed_consistency is None
    assert "ais_track_has_insufficient_speed_history" in result.missing_evidence
