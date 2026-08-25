"""
VARUNA GRID — CASE-0001 Deterministic Integration Fixture.

Generates a synthetic case with known ground truth for E2E testing.
Ground truth is used ONLY for assertion, never passed to inference.
"""
import numpy as np
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import VesselTrack, AISPoint, VesselType
from varuna_prativartan.current_field import SyntheticTruthCurrentField, SyntheticWindField
from varuna_prativartan.engine import advect_particles


def generate_case_0001():
    """
    Generate CASE-0001: a synthetic known-source attribution case.

    Returns:
        dict with keys: slick_lons, slick_lats, tracks, obs_time_hours,
        true_mmsi, seed, config
    """
    seed = 20260825
    rng = np.random.default_rng(seed)

    obs_time_hours = 120.0
    true_age_hours = 24.0
    release_time = obs_time_hours - true_age_hours

    base_lon, base_lat = 72.0, 15.0
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

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
        mmsi="CASE0001_TRUE", vessel_type=VesselType.TANKER, points=truth_points,
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

    # 3. Decoy tracks (source-independent)
    slick_clon = float(np.mean(slick_lons))
    slick_clat = float(np.mean(slick_lats))
    decoy_tracks = []
    for i in range(4):
        d_lon = rng.uniform(slick_clon - 0.5, slick_clon + 0.5)
        d_lat = rng.uniform(slick_clat - 0.5, slick_clat + 0.5)
        d_vu = rng.normal(0.0, 0.04)
        d_vv = rng.normal(0.0, 0.04)
        d_points = []
        for t in times:
            lon = d_lon + d_vu * (t - release_time)
            lat = d_lat + d_vv * (t - release_time)
            dt = base_time + timedelta(hours=t)
            d_points.append(AISPoint(
                timestamp=dt, lon=lon, lat=lat, sog_knots=5.0, heading_deg=0.0,
            ))
        decoy_tracks.append(VesselTrack(
            mmsi=f"DECOY_{i:04d}", vessel_type=VesselType.CARGO, points=d_points,
        ))

    all_tracks = decoy_tracks + [truth_track]

    return {
        "slick_lons": slick_lons,
        "slick_lats": slick_lats,
        "tracks": all_tracks,
        "obs_time_hours": obs_time_hours,
        "true_mmsi": "CASE0001_TRUE",  # ONLY for assertion
        "seed": seed,
        "config": {
            "age_prior_mean": 36.0,
            "age_prior_std": 24.0,
            "latent_prior": 0.5,
            "corridor_width_km": 5.0,
        },
    }
