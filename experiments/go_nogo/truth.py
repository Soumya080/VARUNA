"""Synthetic truth generation for the go/no-go experiment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.forcing import DEG_LAT_KM, StructuredForcing, advect
from experiments.go_nogo.slick import ObservedSlick, make_observed_slick


@dataclass(frozen=True)
class ReleaseTruth:
    release_id: str
    lon: float
    lat: float
    release_time_hours: float
    slick_age_hours: float
    observation_time_hours: float


def generate_truth(
    trial_key: str,
    slick_age_hours: float,
    config: ExperimentConfig,
    rng: np.random.Generator,
) -> ReleaseTruth:
    return ReleaseTruth(
        release_id=f"truth-{trial_key}",
        lon=config.release_lon + float(rng.normal(0.0, 0.015)),
        lat=config.release_lat + float(rng.normal(0.0, 0.015)),
        release_time_hours=0.0,
        slick_age_hours=slick_age_hours,
        observation_time_hours=slick_age_hours if config.observation_time_hours is None
        else config.observation_time_hours,
    )


def generate_slick(
    trial_key: str,
    truth: ReleaseTruth,
    forcing: StructuredForcing,
    config: ExperimentConfig,
    rng: np.random.Generator,
) -> ObservedSlick:
    sigma_lat = config.release_radius_km / DEG_LAT_KM
    sigma_lon = sigma_lat / max(np.cos(np.radians(truth.lat)), 0.01)
    start_lons = truth.lon + rng.normal(0.0, sigma_lon, config.n_forward_particles)
    start_lats = truth.lat + rng.normal(0.0, sigma_lat, config.n_forward_particles)
    hist_lon, hist_lat, _ = advect(
        start_lons,
        start_lats,
        forcing,
        start_time_hours=truth.release_time_hours,
        duration_hours=truth.slick_age_hours,
        dt_seconds=config.dt_seconds,
        wind_drift_factor=config.wind_drift_factor,
        diffusivity_m2s=config.diffusivity_m2s,
        rng=rng,
        backward=False,
    )
    return make_observed_slick(
        slick_id=f"slick-{trial_key}",
        observation_time_hours=truth.observation_time_hours,
        lons=hist_lon[-1],
        lats=hist_lat[-1],
        rng=rng,
    )
