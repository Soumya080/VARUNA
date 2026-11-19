"""Baselines for the fair go/no-go experiment."""

from __future__ import annotations

from experiments.go_nogo.candidates import CandidateTrack
from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.forcing import StructuredForcing, advect
from experiments.go_nogo.nyaya import _closest_approach_km
from experiments.go_nogo.slick import ObservedSlick

import numpy as np


def nearest_vessel_rank(slick: ObservedSlick, candidates: list[CandidateTrack]) -> list[str]:
    obs = slick.observation_time_hours
    scored = []
    for track in candidates:
        lon = float(np.interp(obs, track.times_hours, track.lons))
        lat = float(np.interp(obs, track.times_hours, track.lats))
        dist = _closest_approach_km(track, slick.centroid_lon, slick.centroid_lat)
        # Prefer the interpolated observation-time point, but keep closest track distance
        # as a fallback for sparse/gapped AIS.
        scored.append((min(dist, _closest_approach_km(track, lon, lat)), track.mmsi))
    return [mmsi for _, mmsi in sorted(scored)]


def deterministic_backtrack_rank(
    slick: ObservedSlick,
    candidates: list[CandidateTrack],
    forcing: StructuredForcing,
    config: ExperimentConfig,
    rng: np.random.Generator,
) -> list[str]:
    indices = rng.integers(0, len(slick.lons), min(80, len(slick.lons)))
    hist_lon, hist_lat, hist_t = advect(
        slick.lons[indices],
        slick.lats[indices],
        forcing,
        start_time_hours=slick.observation_time_hours,
        duration_hours=slick.age_prior_mean_hours,
        dt_seconds=config.dt_seconds,
        wind_drift_factor=config.wind_drift_factor,
        diffusivity_m2s=0.0,
        rng=rng,
        backward=True,
    )
    origin_lon = float(np.mean(hist_lon[-1]))
    origin_lat = float(np.mean(hist_lat[-1]))
    origin_time = float(hist_t[-1])
    scored = []
    for track in candidates:
        lon = float(np.interp(origin_time, track.times_hours, track.lons))
        lat = float(np.interp(origin_time, track.times_hours, track.lats))
        scored.append((_closest_approach_km(track, lon, lat) + _closest_approach_km(track, origin_lon, origin_lat), track.mmsi))
    return [mmsi for _, mmsi in sorted(scored)]
