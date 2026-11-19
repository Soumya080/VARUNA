"""
VARUNA GRID — Corridor Mask and Phi Integration Utility.
"""
import numpy as np
from typing import List
from datetime import datetime, timezone
from varuna_contracts.schemas import VesselTrack
from varuna_geospatial.utils import haversine_km_vec

_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)

def build_corridor_mask(
    track: VesselTrack,
    phi_data: np.ndarray,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,
    corridor_width_km: float = 5.0
) -> np.ndarray:
    """Build a boolean mask for the corridor of a given vessel track."""
    covered = np.zeros_like(phi_data, dtype=bool)
    lon_centers = 0.5 * (lon_edges[:-1] + lon_edges[1:])
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    time_centers = 0.5 * (time_edges[:-1] + time_edges[1:])
    n_t, n_y, n_x = phi_data.shape
    lon_mesh, lat_mesh = np.meshgrid(lon_centers, lat_centers)
    lon_flat = lon_mesh.ravel()
    lat_flat = lat_mesh.ravel()
    base_ts = _BASE_TIME.timestamp()

    for point in track.points:
        t_hours = (point.timestamp.timestamp() - base_ts) / 3600.0
        # Only process if within Phi temporal bounds
        if t_hours < time_edges[0] or t_hours > time_edges[-1]:
            continue
        t_idx = int(np.argmin(np.abs(time_centers - t_hours)))
        if 0 <= t_idx < n_t:
            dists = haversine_km_vec(lon_flat, lat_flat, point.lon, point.lat)
            dists_2d = dists.reshape((n_y, n_x))
            covered[t_idx, dists_2d < corridor_width_km] = True
    return covered


def build_union_mask(masks: List[np.ndarray]) -> np.ndarray:
    """Build the union of multiple boolean masks."""
    if not masks:
        return None
    union_mask = np.zeros_like(masks[0], dtype=bool)
    for mask in masks:
        union_mask |= mask
    return union_mask


def integrate_phi_over_mask(phi_data: np.ndarray, mask: np.ndarray) -> float:
    """Integrate the Phi mass over the given boolean mask."""
    if mask is None:
        return 0.0
    return float(phi_data[mask].sum())
