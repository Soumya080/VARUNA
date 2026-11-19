"""Synthetic observed slick construction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from experiments.go_nogo.forcing import DEG_LAT_KM


@dataclass(frozen=True)
class ObservedSlick:
    slick_id: str
    observation_time_hours: float
    lons: np.ndarray
    lats: np.ndarray
    centroid_lon: float
    centroid_lat: float
    age_prior_mean_hours: float
    age_prior_std_hours: float


def infer_age_prior_from_slick(
    lons: np.ndarray,
    lats: np.ndarray,
    *,
    observation_time_hours: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Estimate a broad age prior from observed spread, not from the true release time."""
    centroid_lon = float(np.mean(lons))
    centroid_lat = float(np.mean(lats))
    cos_lat = max(np.cos(np.radians(centroid_lat)), 0.01)
    dx = (lons - centroid_lon) * DEG_LAT_KM * cos_lat
    dy = (lats - centroid_lat) * DEG_LAT_KM
    radius_km = float(np.percentile(np.hypot(dx, dy), 80))

    # This is a deliberately weak stand-in for NETRA's age distribution. It uses only
    # slick morphology and a stochastic residual, so the inverse model does not receive
    # the true age as an input.
    mean_hours = np.clip((radius_km / 1.4) ** 1.35 + rng.normal(0.0, 4.0), 1.5, 72.0)
    std_hours = np.clip(0.35 * mean_hours + rng.uniform(2.0, 6.0), 2.0, 30.0)
    mean_hours = min(float(mean_hours), observation_time_hours + 12.0)
    return float(mean_hours), float(std_hours)


def make_observed_slick(
    slick_id: str,
    observation_time_hours: float,
    lons: np.ndarray,
    lats: np.ndarray,
    rng: np.random.Generator,
) -> ObservedSlick:
    mean_age, std_age = infer_age_prior_from_slick(
        lons,
        lats,
        observation_time_hours=observation_time_hours,
        rng=rng,
    )
    return ObservedSlick(
        slick_id=slick_id,
        observation_time_hours=observation_time_hours,
        lons=lons,
        lats=lats,
        centroid_lon=float(np.mean(lons)),
        centroid_lat=float(np.mean(lats)),
        age_prior_mean_hours=mean_age,
        age_prior_std_hours=std_age,
    )
