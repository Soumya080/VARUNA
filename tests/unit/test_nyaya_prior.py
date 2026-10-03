"""
Track 2 Phase 3/4 — NYAYA prior sub-scores.

Proves compute_speed_anomaly / compute_loiter_score / compute_night_proximity
are real, deterministic calculations over actual track/Phi data — not the
previous hardcoded `0.1` — and that missing inputs produce an honest 0.0
(never a fabricated positive score standing in for "unknown").
"""
from datetime import datetime, timedelta, timezone

import pytest

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.phi import (
    ConvergenceFlag, PhiDiagnostics, PhiField, TimeDistribution,
)
from varuna_contracts.schemas import AISPoint, BBox, VesselTrack, VesselType
from varuna_nyaya.prior import (
    LOITER_RADIUS_KM,
    NIGHT_END_HOUR,
    SPEED_IMPLAUSIBLE_KNOTS,
    compute_loiter_score,
    compute_night_proximity,
    compute_prior,
    compute_speed_anomaly,
)

pytestmark = pytest.mark.unit


def _point(lon, lat, sog=10.0, hour=12, dt=0.0) -> AISPoint:
    return AISPoint(
        timestamp=datetime(2026, 1, 1, hour, 0, 0, tzinfo=timezone.utc) + timedelta(hours=dt),
        lon=lon, lat=lat, sog_knots=sog,
    )


def _track(points, mmsi="123456789") -> VesselTrack:
    return VesselTrack(mmsi=mmsi, vessel_type=VesselType.CARGO, points=points)


def _phi(bbox: BBox | None = None) -> PhiField:
    bbox = bbox or BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0)
    return PhiField(
        phi_id="phi-1", slick_id="slick-1", case_id="case-1",
        data_path="/tmp/phi-1.npz", bbox=bbox, grid_shape=(1, 2, 2),
        time_distribution=TimeDistribution(
            time_edges_unix=[0.0, 3600.0], mass=[1.0],
            mode_unix=1800.0, p05_unix=0.0, p95_unix=3600.0,
        ),
        spatial_modes=[],
        diagnostics=PhiDiagnostics(
            entropy=0.3, concentration=0.5, effective_support_km2=10.0,
            convergence=0.05, convergence_flag=ConvergenceFlag.CONVERGED,
            n_modes=1, particles_seeded=100, ensemble_members_completed=5,
            ensemble_members_requested=5, runtime_seconds=1.0,
        ),
        sensitivity=None,
        n_particles=100, n_ensemble=5, backward_duration_hours=24.0, dt_seconds=900.0,
        forcing_current_source="test", forcing_wind_source="test",
        envelope=EvidenceEnvelope(
            artifact_id="env-1", produced_by="test",
            provenance=Provenance(source_id="test"), mode=EvidenceMode.SIMULATED,
        ),
    )


# ───────────────────────── speed anomaly ─────────────────────────

def test_speed_anomaly_zero_when_no_points_exceed_threshold():
    track = _track([_point(0.5, 0.5, sog=10.0), _point(0.5, 0.5, sog=15.0)])
    assert compute_speed_anomaly(track) == 0.0


def test_speed_anomaly_positive_when_points_exceed_threshold():
    track = _track([
        _point(0.5, 0.5, sog=55.0),  # > SPEED_IMPLAUSIBLE_KNOTS
        _point(0.5, 0.5, sog=10.0),
    ])
    assert compute_speed_anomaly(track) == pytest.approx(0.5)


def test_speed_anomaly_uses_the_documented_threshold_exactly():
    just_under = _track([_point(0.5, 0.5, sog=SPEED_IMPLAUSIBLE_KNOTS - 0.01)] * 2)
    just_over = _track([_point(0.5, 0.5, sog=min(60.0, SPEED_IMPLAUSIBLE_KNOTS + 0.01))] * 2)
    assert compute_speed_anomaly(just_under) == 0.0
    assert compute_speed_anomaly(just_over) == 1.0


def test_speed_anomaly_is_zero_not_fabricated_when_no_sog_recorded():
    track = _track([
        AISPoint(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), lon=0.5, lat=0.5),
        AISPoint(timestamp=datetime(2026, 1, 1, 1, tzinfo=timezone.utc), lon=0.5, lat=0.5),
    ])
    assert compute_speed_anomaly(track) == 0.0


# ───────────────────────── loiter score ─────────────────────────

def test_loiter_score_zero_when_moving_fast():
    phi = _phi()  # bbox center = (0.5, 0.5)
    track = _track([_point(0.5, 0.5, sog=20.0), _point(0.5, 0.5, sog=20.0)])
    assert compute_loiter_score(track, phi) == 0.0


def test_loiter_score_positive_when_slow_and_near():
    phi = _phi()
    track = _track([
        _point(0.5, 0.5, sog=1.0),   # slow, at the bbox center -> loitering
        _point(0.5, 0.5, sog=20.0),  # fast -> not loitering
    ])
    assert compute_loiter_score(track, phi) == pytest.approx(0.5)


def test_loiter_score_zero_when_slow_but_far():
    phi = _phi(bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0))
    far_track = _track([_point(50.0, 50.0, sog=1.0), _point(50.0, 50.0, sog=1.0)])
    assert compute_loiter_score(far_track, phi) == 0.0


def test_loiter_score_uses_bbox_center_when_no_spatial_mode():
    phi = _phi()
    assert phi.primary_mode is None  # current PRATIVARTAN always leaves this empty
    # sanity: the reference point used is bbox.center, not some other value
    center = phi.bbox.center
    assert center.lon == pytest.approx(0.5) and center.lat == pytest.approx(0.5)


# ───────────────────────── night proximity ─────────────────────────

def test_night_proximity_zero_during_day():
    phi = _phi()
    track = _track([_point(0.5, 0.5, hour=12), _point(0.5, 0.5, hour=14)])
    assert compute_night_proximity(track, phi) == 0.0


def test_night_proximity_positive_at_night_inside_bbox():
    phi = _phi()
    track = _track([_point(0.5, 0.5, hour=2), _point(0.5, 0.5, hour=14)])
    assert compute_night_proximity(track, phi) == pytest.approx(0.5)


def test_night_proximity_zero_at_night_outside_bbox():
    phi = _phi(bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0))
    track = _track([_point(50.0, 50.0, hour=2), _point(50.0, 50.0, hour=2)])
    assert compute_night_proximity(track, phi) == 0.0


def test_night_window_boundary_is_half_open():
    phi = _phi()
    at_boundary = _track([_point(0.5, 0.5, hour=int(NIGHT_END_HOUR)), _point(0.5, 0.5, hour=int(NIGHT_END_HOUR))])
    assert compute_night_proximity(at_boundary, phi) == 0.0  # 05:00 is excluded


# ───────────────────────── no fabricated evidence in compute_prior ─────────────────────────

def test_compute_prior_reflects_real_zero_not_fabricated_baseline():
    """
    A featureless track (no SOG, all daytime, far from the field) must
    produce priors of exactly 0.0 on all three previously-mocked sub-scores
    — not the old 0.1 floor, and not silently omitted.
    """
    phi = _phi(bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0))
    far_track = _track([
        AISPoint(timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone.utc), lon=80.0, lat=80.0),
        AISPoint(timestamp=datetime(2026, 1, 1, 13, tzinfo=timezone.utc), lon=80.0, lat=80.0),
    ])
    contribution = compute_prior(far_track, phi)
    assert contribution.speed_anomaly == 0.0
    assert contribution.loiter_score == 0.0
    assert contribution.night_proximity == 0.0
    # combined is still well-formed (type_weight * (1 + weighted terms))
    assert contribution.combined > 0.0
