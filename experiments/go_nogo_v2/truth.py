"""
VARUNA GRID — Go/No-Go v2 Truth Generation.
"""
import numpy as np
from typing import Tuple, List, Optional
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import VesselTrack, AISPoint, VesselType
from varuna_prativartan.current_field import SyntheticTruthCurrentField, SyntheticWindField
from varuna_prativartan.engine import advect_particles

def generate_case(
    seed: int,
    obs_time_hours: float,
    true_age_hours: float,
    is_latent: bool,
    n_decoys: int = 4
) -> Tuple[np.ndarray, np.ndarray, VesselTrack, List[VesselTrack]]:
    """
    Returns:
        (slick_lons, slick_lats, truth_track, decoy_tracks)
    """
    rng = np.random.default_rng(seed)
    
    # 1. Generate Truth track
    release_time_hours = obs_time_hours - true_age_hours
    
    # Base location for the experiment
    base_lon, base_lat = 72.0, 15.0
    
    # Generate the trajectory of the true vessel
    t_start = max(0, release_time_hours - 24.0)
    t_end = min(obs_time_hours + 24.0, 200.0)
    times = np.arange(t_start, t_end, 0.25)
    
    v_u = rng.normal(0.05, 0.02)
    v_v = rng.normal(0.05, 0.02)
    
    truth_points = []
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    release_lon, release_lat = base_lon, base_lat
    
    for t in times:
        lon = base_lon + v_u * (t - release_time_hours)
        lat = base_lat + v_v * (t - release_time_hours)
        dt = base_time + timedelta(hours=t)
        truth_points.append(AISPoint(timestamp=dt, lon=lon, lat=lat, sog_knots=5.0, heading_deg=45.0))
        if abs(t - release_time_hours) < 0.1:
            release_lon, release_lat = lon, lat
            
    truth_track = VesselTrack(
        mmsi="123456789" if not is_latent else "LATENT_TRUTH",
        vessel_type=VesselType.TANKER,
        points=truth_points
    )
    
    # 2. Generate slick at obs_time_hours by forward advecting from release point
    current = SyntheticTruthCurrentField()
    wind = SyntheticWindField()
    
    # Initial slick points
    n_slick = 500
    slick_lons_init = rng.normal(release_lon, 0.01, n_slick)
    slick_lats_init = rng.normal(release_lat, 0.01, n_slick)
    
    # Forward advect
    lons_f, lats_f, _ = advect_particles(
        lons=slick_lons_init,
        lats=slick_lats_init,
        current=current,
        wind=wind,
        wind_drift_factor=0.03,
        diffusivity=10.0,
        duration_hours=true_age_hours,
        dt_seconds=900,
        rng=rng,
        start_time_hours=release_time_hours,
        backward=False
    )
    
    slick_lons = lons_f[:, -1]
    slick_lats = lats_f[:, -1]
    
    # 3. Generate Decoy tracks (hard negatives)
    decoy_tracks = []
    for i in range(n_decoys):
        # Place decoys near the release point at the release time
        d_lon = release_lon + rng.normal(0, 0.1)
        d_lat = release_lat + rng.normal(0, 0.1)
        
        d_v_u = rng.normal(-0.02, 0.05)
        d_v_v = rng.normal(0.04, 0.05)
        
        d_points = []
        for t in times:
            lon = d_lon + d_v_u * (t - release_time_hours)
            lat = d_lat + d_v_v * (t - release_time_hours)
            dt = base_time + timedelta(hours=t)
            d_points.append(AISPoint(timestamp=dt, lon=lon, lat=lat, sog_knots=5.0, heading_deg=0.0))
            
        decoy_tracks.append(VesselTrack(
            mmsi=f"98765432{i}",
            vessel_type=VesselType.CARGO,
            points=d_points
        ))
        
    return slick_lons, slick_lats, truth_track, decoy_tracks
