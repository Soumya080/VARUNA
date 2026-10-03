"""Independent synthetic AIS candidate generation with hard negatives."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.forcing import DEG_LAT_KM
from experiments.go_nogo.truth import ReleaseTruth


@dataclass(frozen=True)
class CandidateTrack:
    mmsi: str
    vessel_name: str
    vessel_type: str
    times_hours: np.ndarray
    lons: np.ndarray
    lats: np.ndarray
    ais_reliability: float
    is_guilty: bool = False

    @property
    def start_time_hours(self) -> float:
        return float(self.times_hours[0])

    @property
    def end_time_hours(self) -> float:
        return float(self.times_hours[-1])


def _track_between(
    mmsi: str,
    vessel_name: str,
    vessel_type: str,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    start_time: float,
    end_time: float,
    *,
    rng: np.random.Generator,
    ais_uncertainty: str,
    is_guilty: bool = False,
) -> CandidateTrack:
    times = np.arange(start_time, end_time + 1e-6, 0.5)
    frac = (times - start_time) / max(end_time - start_time, 1e-9)
    wiggle = 0.006 * np.sin(2.0 * np.pi * frac + rng.uniform(0.0, 2.0 * np.pi))
    lons = start_lon + frac * (end_lon - start_lon) + wiggle
    lats = start_lat + frac * (end_lat - start_lat) + 0.6 * wiggle
    reliability = 1.0

    if ais_uncertainty == "noisy":
        lons = lons + rng.normal(0.0, 0.006, len(lons))
        lats = lats + rng.normal(0.0, 0.006, len(lats))
        reliability = 0.85
    elif ais_uncertainty == "gaps":
        keep = np.ones(len(times), dtype=bool)
        if len(times) > 8:
            gap_start = int(rng.integers(3, max(4, len(times) - 5)))
            keep[gap_start:gap_start + 3] = False
        times, lons, lats = times[keep], lons[keep], lats[keep]
        reliability = 0.78
    elif ais_uncertainty != "clean":
        raise ValueError(f"unknown AIS uncertainty: {ais_uncertainty}")

    return CandidateTrack(
        mmsi=mmsi,
        vessel_name=vessel_name,
        vessel_type=vessel_type,
        times_hours=times,
        lons=lons,
        lats=lats,
        ais_reliability=reliability,
        is_guilty=is_guilty,
    )


def _line_through_point(
    truth: ReleaseTruth,
    start_time: float,
    end_time: float,
    *,
    rng: np.random.Generator,
    miss_km: float,
) -> tuple[float, float, float, float]:
    bearing = rng.uniform(0.0, 2.0 * np.pi)
    speed_kmh = rng.uniform(18.0, 34.0)
    total_hours = end_time - start_time
    half_len_km = 0.5 * speed_kmh * total_hours
    offset_angle = bearing + np.pi / 2.0
    offset_km = rng.normal(0.0, miss_km)

    center_lon = truth.lon + (offset_km * np.cos(offset_angle)) / (
        DEG_LAT_KM * max(np.cos(np.radians(truth.lat)), 0.01)
    )
    center_lat = truth.lat + (offset_km * np.sin(offset_angle)) / DEG_LAT_KM
    dlon = (half_len_km * np.cos(bearing)) / (
        DEG_LAT_KM * max(np.cos(np.radians(truth.lat)), 0.01)
    )
    dlat = (half_len_km * np.sin(bearing)) / DEG_LAT_KM
    return center_lon - dlon, center_lat - dlat, center_lon + dlon, center_lat + dlat


def generate_candidates(
    truth: ReleaseTruth,
    n_candidates: int,
    ais_uncertainty: str,
    config: ExperimentConfig,
    rng: np.random.Generator,
) -> list[CandidateTrack]:
    """Generate traffic without handing candidate scoring any truth fields."""
    start_time = truth.release_time_hours - 6.0
    end_time = truth.observation_time_hours + 6.0
    tracks: list[CandidateTrack] = []

    start_lon, start_lat, end_lon, end_lat = _line_through_point(
        truth,
        start_time,
        end_time,
        rng=rng,
        miss_km=0.6,
    )
    tracks.append(
        _track_between(
            "999000001",
            "SYNTHETIC_GUILTY",
            "tanker",
            start_lon,
            start_lat,
            end_lon,
            end_lat,
            start_time,
            end_time,
            rng=rng,
            ais_uncertainty=ais_uncertainty,
            is_guilty=True,
        )
    )

    n_hard = int(round((n_candidates - 1) * config.hard_negative_fraction))
    vessel_types = ("tanker", "cargo", "fishing", "passenger", "unknown")
    for idx in range(n_candidates - 1):
        is_hard = idx < n_hard
        if is_hard:
            endpoints = _line_through_point(
                truth,
                start_time,
                end_time,
                rng=rng,
                miss_km=float(rng.uniform(1.5, 7.0)),
            )
        else:
            box_km = 70.0
            lon_span = box_km / (DEG_LAT_KM * max(np.cos(np.radians(truth.lat)), 0.01))
            lat_span = box_km / DEG_LAT_KM
            endpoints = (
                truth.lon + rng.uniform(-lon_span, lon_span),
                truth.lat + rng.uniform(-lat_span, lat_span),
                truth.lon + rng.uniform(-lon_span, lon_span),
                truth.lat + rng.uniform(-lat_span, lat_span),
            )
        tracks.append(
            _track_between(
                f"999{idx + 2:06d}",
                f"SYNTHETIC_{idx + 2:03d}",
                str(rng.choice(vessel_types)),
                *endpoints,
                start_time,
                end_time,
                rng=rng,
                ais_uncertainty=ais_uncertainty,
            )
        )

    rng.shuffle(tracks)
    return tracks
