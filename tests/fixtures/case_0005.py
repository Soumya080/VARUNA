"""
VARUNA GRID — CASE-0005 Deterministic Integration Fixture.

SOFTWARE REGRESSION FIXTURE — NOT SCIENTIFIC BENCHMARK.

Edge case: No candidates. Decoy tracks are far away.
This fixture verifies system behaviour under controlled conditions.
It MUST NOT be cited as evidence of scientific accuracy or operational
readiness. Scientific validation belongs to M2.2 (deferred).
"""
import numpy as np
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import VesselTrack, AISPoint, VesselType
from varuna_prativartan.current_field import SyntheticTruthCurrentField, SyntheticWindField
from varuna_prativartan.engine import advect_particles


def generate_case_0005():
    seed = 20260829
    rng = np.random.default_rng(seed)

    obs_time_hours = 120.0
    true_age_hours = 24.0
    release_time = obs_time_hours - true_age_hours

    base_lon, base_lat = 72.0, 15.0
    base_time = datetime(2026, 5, 1, tzinfo=timezone.utc)

    # We do NOT include the true track in the track list this time!
    # Instead, we just have decoy tracks far away.

    # 1. Forward-advect slick from release location
    release_lon, release_lat = base_lon, base_lat
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

    # 2. Decoy tracks far away
    t_start = max(0, release_time - 24.0)
    t_end = min(obs_time_hours + 24.0, 200.0)
    times = np.arange(t_start, t_end, 0.5)

    slick_clon = float(np.mean(slick_lons))
    slick_clat = float(np.mean(slick_lats))
    decoy_tracks = []
    for i in range(2):
        d_lon = slick_clon + 5.0  # 5 degrees away!
        d_lat = slick_clat + 5.0
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

    all_tracks = decoy_tracks

    return {
        "slick_lons": slick_lons,
        "slick_lats": slick_lats,
        "tracks": all_tracks,
        "obs_time_hours": obs_time_hours,
        "true_mmsi": None,
        "seed": seed,
        "config": {
            "age_prior_mean": 36.0,
            "age_prior_std": 24.0,
            "latent_prior": 0.5,
            "corridor_width_km": 5.0,
        },
    }
