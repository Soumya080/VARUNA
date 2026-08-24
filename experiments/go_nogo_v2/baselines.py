"""
VARUNA GRID — Baseline Comparison Models.
"""
import numpy as np
from datetime import datetime, timezone
from typing import List, Tuple
from varuna_contracts.schemas import VesselTrack
from varuna_geospatial.utils import haversine_km_vec

def naive_distance_baseline(
    tracks: List[VesselTrack],
    slick_lons: np.ndarray,
    slick_lats: np.ndarray,
    obs_time_hours: float
) -> str:
    """
    Finds the closest vessel to the slick center at the time of observation.
    """
    if not tracks:
        return "LATENT_SOURCE"
        
    slick_center_lon = np.mean(slick_lons)
    slick_center_lat = np.mean(slick_lats)
    
    min_dist = float('inf')
    best_mmsi = "LATENT_SOURCE"
    
    for track in tracks:
        min_time_diff = float('inf')
        closest_lon, closest_lat = None, None
        
        for p in track.points:
            base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            t_hours = (p.timestamp - base_time).total_seconds() / 3600.0
            diff = abs(t_hours - obs_time_hours)
            if diff < min_time_diff:
                min_time_diff = diff
                closest_lon = p.lon
                closest_lat = p.lat
                
        if closest_lon is not None:
            dists = haversine_km_vec(
                np.array([closest_lon]), np.array([closest_lat]),
                slick_center_lon, slick_center_lat
            )
            if dists[0] < min_dist:
                min_dist = dists[0]
                best_mmsi = track.mmsi
                
    if min_dist > 100.0:
        return "LATENT_SOURCE"
        
    return best_mmsi

def uncalibrated_prativartan_baseline(
    tracks: List[VesselTrack],
    posterior: dict
) -> str:
    """
    Just picks the argmax of the posterior.
    """
    if not posterior:
        return "LATENT_SOURCE"
    
    best_mmsi = max(posterior.items(), key=lambda x: x[1])[0]
    return best_mmsi
