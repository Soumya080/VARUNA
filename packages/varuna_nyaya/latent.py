"""
VARUNA GRID — Latent-source hypothesis L₀ computation via corridor subtraction.
"""
import numpy as np
from typing import List
from datetime import datetime, timezone
from varuna_contracts.schemas import VesselTrack
from varuna_geospatial.utils import haversine_km_vec

_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def compute_latent_probability(
    phi_data: np.ndarray,      # (n_t, n_y, n_x)
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,    # in hours from epoch
    tracks: List[VesselTrack],
    corridor_width_km: float = 5.0,
) -> float:
    """
    L₀ = 1 − Σ Φ[cells inside ANY track corridor]
    """
    covered = np.zeros_like(phi_data, dtype=bool)

    lon_centers = 0.5 * (lon_edges[:-1] + lon_edges[1:])
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    time_centers = 0.5 * (time_edges[:-1] + time_edges[1:])

    n_t, n_y, n_x = phi_data.shape

    # Meshgrid for vectorized distance computation
    lon_mesh, lat_mesh = np.meshgrid(lon_centers, lat_centers)
    lon_flat = lon_mesh.ravel()
    lat_flat = lat_mesh.ravel()

    base_ts = _BASE_TIME.timestamp()

    for track in tracks:
        for point in track.points:
            t_hours = (point.timestamp.timestamp() - base_ts) / 3600.0
            t_idx = int(np.argmin(np.abs(time_centers - t_hours)))

            dists = haversine_km_vec(
                lon_flat, lat_flat,
                point.lon, point.lat
            )

            dists_2d = dists.reshape((n_y, n_x))
            covered[t_idx, dists_2d < corridor_width_km] = True

    residual_mass = float(phi_data[~covered].sum())
    return residual_mass
