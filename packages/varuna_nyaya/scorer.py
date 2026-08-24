"""
VARUNA GRID — Path-integral likelihood computation.
"""
import numpy as np
from datetime import datetime, timezone
from varuna_contracts.phi import PhiField
from varuna_contracts.schemas import VesselTrack

# Must match the epoch used in truth.py and phi_builder.py
_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)

def compute_path_integral(
    track: VesselTrack,
    phi: PhiField,
) -> float:
    """
    L_k = Σ_i Φ[t_i, y_i, x_i] · Δt_i

    time_edges in the .npz are in HOURS from 2026-01-01 UTC.
    Track timestamps are datetime objects — converted to the same unit.
    """
    data = np.load(phi.data_path)
    phi_data = data['phi']
    lon_edges = data['lon_edges']
    lat_edges = data['lat_edges']
    time_edges = data['time_edges']   # in hours

    base_ts = _BASE_TIME.timestamp()
    timestamps_hours = np.array([
        (p.timestamp.timestamp() - base_ts) / 3600.0
        for p in track.points
    ])
    lons = np.array([p.lon for p in track.points])
    lats = np.array([p.lat for p in track.points])

    if len(timestamps_hours) == 0:
        return 0.0

    t_idx = np.digitize(timestamps_hours, time_edges) - 1
    y_idx = np.digitize(lats, lat_edges) - 1
    x_idx = np.digitize(lons, lon_edges) - 1

    n_t, n_y, n_x = phi_data.shape
    valid = (
        (t_idx >= 0) & (t_idx < n_t) &
        (y_idx >= 0) & (y_idx < n_y) &
        (x_idx >= 0) & (x_idx < n_x)
    )

    if not valid.any():
        return 0.0

    dt = np.diff(timestamps_hours, prepend=timestamps_hours[0])
    dt[0] = dt[1] if len(dt) > 1 else 1.0
    dt = np.abs(dt)

    phi_values = phi_data[t_idx[valid], y_idx[valid], x_idx[valid]]
    L_k = float(np.sum(phi_values * dt[valid]))
    return L_k
