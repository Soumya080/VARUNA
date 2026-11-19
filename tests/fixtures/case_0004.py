"""
VARUNA GRID — CASE-0004 Deterministic Integration Fixture.

SOFTWARE REGRESSION FIXTURE — NOT SCIENTIFIC BENCHMARK.

Ambiguous attribution case: Inconclusive.
This fixture verifies system behaviour under controlled conditions.
It MUST NOT be cited as evidence of scientific accuracy or operational
readiness. Scientific validation belongs to M2.2 (deferred).
"""
import numpy as np
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import VesselTrack, AISPoint, VesselType
from varuna_prativartan.current_field import SyntheticTruthCurrentField, SyntheticWindField
from varuna_prativartan.engine import advect_particles


def generate_case_0004():
    seed = 20260828
    rng = np.random.default_rng(seed)

    obs_time_hours = 120.0
    true_age_hours = 24.0
    release_time = obs_time_hours - true_age_hours

    base_lon, base_lat = 72.0, 15.0
    base_time = datetime(2026, 4, 1, tzinfo=timezone.utc)

    # 1. True vessel track
    t_start = max(0, release_time - 24.0)
    t_end = min(obs_time_hours + 24.0, 200.0)
    times = np.arange(t_start, t_end, 0.5)

    v_u, v_v = 0.05, 0.03
    truth_points = []
    release_lon, release_lat = base_lon, base_lat
    for t in times:
        lon = base_lon + v_u * (t - release_time)
        lat = base_lat + v_v * (t - release_time)
        dt = base_time + timedelta(hours=t)
        truth_points.append(AISPoint(
            timestamp=dt, lon=lon, lat=lat, sog_knots=5.0, heading_deg=45.0,
        ))
        if abs(t - release_time) < 0.3:
            release_lon, release_lat = lon, lat

    truth_track = VesselTrack(
        mmsi="CASE0004_TRUE", vessel_type=VesselType.TANKER, points=truth_points,
    )

    # 2. Forward-advect slick
    current = SyntheticTruthCurrentField()
    wind = SyntheticWindField()
    n_slick = 300
    slick_init_lons = rng.normal(release_lon, 0.01, n_slick)
    slick_init_lats = rng.normal(release_lat, 0.01, n_slick)

    lons_f, lats_f, _ = advect_particles(
        lons=slick_init_lons, lats=slick_init_lats,
        current=current, wind=wind,
        wind_drift_factor=0.03, diffusivity=10.0,
        duration_hours=true_age_hours, dt_seconds=900,
        rng=rng, start_time_hours=release_time, backward=False,
    )
    slick_lons = lons_f[:, -1]
    slick_lats = lats_f[:, -1]

    # 3. Very close decoy track to cause ambiguity
    ambiguous_points = []
    for t in times:
        lon = base_lon + (v_u + 0.002) * (t - release_time)
        lat = base_lat + (v_v - 0.002) * (t - release_time)
        dt = base_time + timedelta(hours=t)
        ambiguous_points.append(AISPoint(
            timestamp=dt, lon=lon, lat=lat, sog_knots=5.0, heading_deg=45.0,
        ))
    ambiguous_track = VesselTrack(
        mmsi="DECOY_AMBIGUOUS", vessel_type=VesselType.TANKER, points=ambiguous_points,
    )

    all_tracks = [ambiguous_track, truth_track]

    return {
        "slick_lons": slick_lons,
        "slick_lats": slick_lats,
        "tracks": all_tracks,
        "obs_time_hours": obs_time_hours,
        "true_mmsi": "CASE0004_TRUE",
        "seed": seed,
        "config": {
            "age_prior_mean": 36.0,
            "age_prior_std": 24.0,
            "latent_prior": 0.5,
            "corridor_width_km": 5.0,
        },
    }
