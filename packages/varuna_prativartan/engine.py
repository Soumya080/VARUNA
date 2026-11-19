"""
VARUNA GRID — Particle advection engine.
"""
from __future__ import annotations
import numpy as np
from typing import Tuple
from varuna_prativartan.current_field import AbstractCurrentField, AbstractWindField

EARTH_RADIUS_M = 6_371_000
DEG_TO_M = 111_320  # approximate meters per degree latitude

def advect_particles(
    lons: np.ndarray,
    lats: np.ndarray,
    current: AbstractCurrentField,
    wind: AbstractWindField,
    wind_drift_factor: float,
    diffusivity: float,
    duration_hours: float,
    dt_seconds: float,
    rng: np.random.Generator,
    current_noise_factor: float = 1.0,
    current_angle_noise_deg: float = 0.0,
    start_time_hours: float = 0.0,
    backward: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Advect particles through the current+wind field using Euler-Maruyama.
    Returns:
        history_lons: shape (N, T)
        history_lats: shape (N, T)
        history_times: shape (T,)
    """
    N = len(lons)
    direction = -1.0 if backward else 1.0
    dt = dt_seconds * direction  

    n_steps = int(abs(duration_hours * 3600 / dt_seconds))
    if n_steps == 0:
        return lons.reshape(-1, 1), lats.reshape(-1, 1), np.array([start_time_hours])

    history_lons = np.zeros((N, n_steps + 1))
    history_lats = np.zeros((N, n_steps + 1))
    history_times = np.zeros(n_steps + 1)

    history_lons[:, 0] = lons.copy()
    history_lats[:, 0] = lats.copy()
    history_times[0] = start_time_hours

    cur_lons = lons.copy()
    cur_lats = lats.copy()

    angle_noise_rad = np.radians(current_angle_noise_deg)
    cos_n, sin_n = np.cos(angle_noise_rad), np.sin(angle_noise_rad)

    sigma = np.sqrt(2 * diffusivity * abs(dt_seconds))

    for step in range(1, n_steps + 1):
        t_hours = start_time_hours + (step * dt / 3600.0)

        u_curr, v_curr = current.velocity_at(cur_lons, cur_lats, t_hours)

        # Apply perturbation
        u_curr *= current_noise_factor
        v_curr *= current_noise_factor
        
        if current_angle_noise_deg != 0.0:
            u_new = u_curr * cos_n - v_curr * sin_n
            v_new = u_curr * sin_n + v_curr * cos_n
            u_curr, v_curr = u_new, v_new

        u_wind, v_wind = wind.velocity_at(cur_lons, cur_lats, t_hours)

        u_total = u_curr + wind_drift_factor * u_wind
        v_total = v_curr + wind_drift_factor * v_wind

        dx = u_total * dt
        dy = v_total * dt

        # Stochastic diffusion using provided rng
        dx += rng.normal(0, sigma, N)
        dy += rng.normal(0, sigma, N)

        cos_lat = np.cos(np.radians(cur_lats))
        cos_lat = np.maximum(cos_lat, 0.01)
        
        dlon = dx / (DEG_TO_M * cos_lat)
        dlat = dy / DEG_TO_M

        cur_lons += dlon
        cur_lats += dlat

        history_lons[:, step] = cur_lons
        history_lats[:, step] = cur_lats
        history_times[step] = t_hours

    return history_lons, history_lats, history_times
