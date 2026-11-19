"""Synthetic forcing with spatial structure and independent inference perturbations."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, radians, sin

import numpy as np

DEG_LAT_KM = 111.32


@dataclass(frozen=True)
class StructuredForcing:
    """A small synthetic current/wind field with shear and eddies.

    This is not a production ocean model. It exists only to make the synthetic inverse
    problem capable of failing before OpenDrift/CMEMS are available.
    """

    current_u_ms: float
    current_v_ms: float
    wind_u_ms: float
    wind_v_ms: float
    shear: float
    eddy_strength: float
    phase: float
    lon0: float
    lat0: float
    structural_bias_u_ms: float = 0.0
    structural_bias_v_ms: float = 0.0
    rotation_bias_deg: float = 0.0

    def current_at(self, lon: np.ndarray, lat: np.ndarray, t_hours: float) -> tuple[np.ndarray, np.ndarray]:
        x = (lon - self.lon0) * DEG_LAT_KM * max(cos(radians(self.lat0)), 0.01)
        y = (lat - self.lat0) * DEG_LAT_KM
        phase = self.phase + 2.0 * pi * t_hours / 36.0

        u = self.current_u_ms + self.shear * y / 50.0
        v = self.current_v_ms - self.shear * x / 50.0
        eddy = self.eddy_strength * np.exp(-((x / 35.0) ** 2 + (y / 35.0) ** 2))
        u = u + eddy * np.sin(y / 12.0 + phase)
        v = v - eddy * np.sin(x / 12.0 - phase)

        if self.rotation_bias_deg:
            angle = radians(self.rotation_bias_deg)
            u, v = u * cos(angle) - v * sin(angle), u * sin(angle) + v * cos(angle)

        return u + self.structural_bias_u_ms, v + self.structural_bias_v_ms

    def wind_at(self, t_hours: float) -> tuple[float, float]:
        phase = self.phase + 2.0 * pi * t_hours / 30.0
        return (
            self.wind_u_ms + 1.2 * sin(phase),
            self.wind_v_ms + 1.0 * cos(0.7 * phase),
        )


def make_truth_forcing(seed: int, lon0: float, lat0: float) -> StructuredForcing:
    rng = np.random.default_rng(seed)
    return StructuredForcing(
        current_u_ms=float(rng.normal(0.16, 0.03)),
        current_v_ms=float(rng.normal(0.06, 0.025)),
        wind_u_ms=float(rng.normal(4.0, 0.8)),
        wind_v_ms=float(rng.normal(1.0, 0.8)),
        shear=float(rng.uniform(0.025, 0.055)),
        eddy_strength=float(rng.uniform(0.025, 0.06)),
        phase=float(rng.uniform(0.0, 2.0 * pi)),
        lon0=lon0,
        lat0=lat0,
    )


def make_inference_forcing(truth: StructuredForcing, perturbation: str, seed: int) -> StructuredForcing:
    rng = np.random.default_rng(seed)
    if perturbation == "baseline":
        scale = 0.4
    elif perturbation == "moderate":
        scale = 1.0
    elif perturbation == "high":
        scale = 1.8
    else:
        raise ValueError(f"unknown forcing perturbation: {perturbation}")

    return StructuredForcing(
        current_u_ms=truth.current_u_ms + float(rng.normal(0.0, 0.015 * scale)),
        current_v_ms=truth.current_v_ms + float(rng.normal(0.0, 0.015 * scale)),
        wind_u_ms=truth.wind_u_ms + float(rng.normal(0.0, 0.35 * scale)),
        wind_v_ms=truth.wind_v_ms + float(rng.normal(0.0, 0.35 * scale)),
        shear=max(0.0, truth.shear + float(rng.normal(0.0, 0.012 * scale))),
        eddy_strength=max(0.0, truth.eddy_strength + float(rng.normal(0.0, 0.012 * scale))),
        phase=truth.phase + float(rng.normal(0.0, 0.25 * scale)),
        lon0=truth.lon0,
        lat0=truth.lat0,
        structural_bias_u_ms=float(rng.normal(0.0, 0.018 * scale)),
        structural_bias_v_ms=float(rng.normal(0.0, 0.018 * scale)),
        rotation_bias_deg=float(rng.normal(0.0, 5.0 * scale)),
    )


def advect(
    lons: np.ndarray,
    lats: np.ndarray,
    forcing: StructuredForcing,
    *,
    start_time_hours: float,
    duration_hours: float,
    dt_seconds: float,
    wind_drift_factor: float,
    diffusivity_m2s: float,
    rng: np.random.Generator,
    backward: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Advect particles forward or backward under the synthetic field."""
    direction = -1.0 if backward else 1.0
    n_steps = max(1, int(round(abs(duration_hours) * 3600.0 / dt_seconds)))
    signed_dt = direction * dt_seconds
    hist_lon = np.empty((n_steps + 1, len(lons)), dtype=np.float64)
    hist_lat = np.empty((n_steps + 1, len(lats)), dtype=np.float64)
    hist_t = np.empty(n_steps + 1, dtype=np.float64)

    cur_lon = lons.astype(np.float64).copy()
    cur_lat = lats.astype(np.float64).copy()
    hist_lon[0] = cur_lon
    hist_lat[0] = cur_lat
    hist_t[0] = start_time_hours

    for step in range(1, n_steps + 1):
        t_hours = start_time_hours + step * signed_dt / 3600.0
        current_u, current_v = forcing.current_at(cur_lon, cur_lat, t_hours)
        wind_u, wind_v = forcing.wind_at(t_hours)
        u_total = current_u + wind_drift_factor * wind_u
        v_total = current_v + wind_drift_factor * wind_v

        sigma_m = (2.0 * diffusivity_m2s * abs(dt_seconds)) ** 0.5
        dx_m = u_total * signed_dt + rng.normal(0.0, sigma_m, len(cur_lon))
        dy_m = v_total * signed_dt + rng.normal(0.0, sigma_m, len(cur_lat))

        cos_lat = np.maximum(np.cos(np.radians(cur_lat)), 0.01)
        cur_lon = cur_lon + dx_m / (1000.0 * DEG_LAT_KM * cos_lat)
        cur_lat = cur_lat + dy_m / (1000.0 * DEG_LAT_KM)
        hist_lon[step] = cur_lon
        hist_lat[step] = cur_lat
        hist_t[step] = t_hours

    return hist_lon, hist_lat, hist_t
