"""NYAYA-style path-integral attribution for the fair experiment."""

from __future__ import annotations

from dataclasses import dataclass
from math import log

import numpy as np

from experiments.go_nogo.candidates import CandidateTrack
from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.forcing import DEG_LAT_KM
from experiments.go_nogo.prativartan import PhiArtifact


@dataclass(frozen=True)
class CandidatePosterior:
    mmsi: str
    vessel_name: str
    posterior: float
    rank: int
    path_integral: float
    likelihood: float
    prior: float
    closest_approach_km: float
    phi_mass_explained: float
    is_guilty: bool


@dataclass(frozen=True)
class Attribution:
    candidates: list[CandidatePosterior]
    latent_probability: float
    posterior_entropy: float
    top_gap: float
    distinguishability: float
    decision_state: str


def _digitized_track(track: CandidateTrack, phi: PhiArtifact) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mask = (track.times_hours >= phi.time_edges[0]) & (track.times_hours <= phi.time_edges[-1])
    times = track.times_hours[mask]
    lons = track.lons[mask]
    lats = track.lats[mask]
    if len(times) == 0:
        return times, np.array([], dtype=int), np.array([], dtype=int), np.array([], dtype=int)
    ti = np.clip(np.digitize(times, phi.time_edges) - 1, 0, phi.phi.shape[0] - 1)
    yi = np.clip(np.digitize(lats, phi.lat_edges) - 1, 0, phi.phi.shape[1] - 1)
    xi = np.clip(np.digitize(lons, phi.lon_edges) - 1, 0, phi.phi.shape[2] - 1)
    return times, ti, yi, xi


def _path_integral(track: CandidateTrack, phi: PhiArtifact) -> float:
    times, ti, yi, xi = _digitized_track(track, phi)
    if len(times) == 0:
        return 0.0
    dt_hours = np.diff(times, prepend=times[0])
    if len(dt_hours) > 1:
        dt_hours[0] = np.median(dt_hours[1:])
    return float(np.sum(phi.phi[ti, yi, xi] * np.maximum(dt_hours, 0.05)))


def _closest_approach_km(track: CandidateTrack, lon: float, lat: float) -> float:
    cos_lat = max(np.cos(np.radians(lat)), 0.01)
    dx = (track.lons - lon) * DEG_LAT_KM * cos_lat
    dy = (track.lats - lat) * DEG_LAT_KM
    return float(np.min(np.hypot(dx, dy)))


def _prior(track: CandidateTrack) -> float:
    type_weight = {
        "tanker": 1.25,
        "cargo": 1.1,
        "fishing": 0.85,
        "passenger": 0.7,
        "unknown": 1.0,
    }.get(track.vessel_type, 1.0)
    # AIS gaps reduce reliability, but they are not treated as suspicious evidence.
    return float(type_weight * (0.75 + 0.25 * track.ais_reliability))


def _explained_mass(tracks: list[CandidateTrack], phi: PhiArtifact, corridor_km: float) -> float:
    t_centers = 0.5 * (phi.time_edges[:-1] + phi.time_edges[1:])
    lon_centers = 0.5 * (phi.lon_edges[:-1] + phi.lon_edges[1:])
    lat_centers = 0.5 * (phi.lat_edges[:-1] + phi.lat_edges[1:])
    explained = np.zeros(phi.phi.shape, dtype=bool)

    for track in tracks:
        if len(track.times_hours) < 2:
            continue
        interp_lon = np.interp(t_centers, track.times_hours, track.lons)
        interp_lat = np.interp(t_centers, track.times_hours, track.lats)
        for ti, (lon, lat) in enumerate(zip(interp_lon, interp_lat, strict=False)):
            cos_lat = max(np.cos(np.radians(float(lat))), 0.01)
            dx = (lon_centers[None, :] - lon) * DEG_LAT_KM * cos_lat
            dy = (lat_centers[:, None] - lat) * DEG_LAT_KM
            explained[ti] |= np.hypot(dx, dy) <= corridor_km
    return float(phi.phi[explained].sum())


def attribute(phi: PhiArtifact, candidates: list[CandidateTrack], config: ExperimentConfig) -> Attribution:
    raw: list[tuple[CandidateTrack, float, float, float, float]] = []
    peak_idx = np.unravel_index(int(np.argmax(phi.phi)), phi.phi.shape)
    peak_lon = float(0.5 * (phi.lon_edges[peak_idx[2]] + phi.lon_edges[peak_idx[2] + 1]))
    peak_lat = float(0.5 * (phi.lat_edges[peak_idx[1]] + phi.lat_edges[peak_idx[1] + 1]))
    for track in candidates:
        integral = _path_integral(track, phi)
        prior = _prior(track)
        likelihood = integral * prior * track.ais_reliability
        closest = _closest_approach_km(track, peak_lon, peak_lat)
        raw.append((track, integral, prior, likelihood, closest))

    explained = _explained_mass(candidates, phi, config.track_corridor_km)
    latent_likelihood = max(1.0 - explained, 0.01) * 0.55
    denom = latent_likelihood + sum(item[3] for item in raw)
    if denom <= 0:
        denom = 1.0
    scored = []
    for track, integral, prior, likelihood, closest in raw:
        posterior = likelihood / denom
        scored.append(
            CandidatePosterior(
                mmsi=track.mmsi,
                vessel_name=track.vessel_name,
                posterior=float(posterior),
                rank=0,
                path_integral=float(integral),
                likelihood=float(likelihood),
                prior=float(prior),
                closest_approach_km=closest,
                phi_mass_explained=float(min(1.0, integral / max(phi.phi.sum(), 1e-9))),
                is_guilty=track.is_guilty,
            )
        )
    scored.sort(key=lambda c: c.posterior, reverse=True)
    ranked = [
        CandidatePosterior(**{**candidate.__dict__, "rank": idx})
        for idx, candidate in enumerate(scored, start=1)
    ]
    latent_probability = float(latent_likelihood / denom)
    probs = [c.posterior for c in ranked] + [latent_probability]
    entropy = 0.0 if len(probs) <= 1 else float(-sum(p * log(max(p, 1e-12)) for p in probs) / log(len(probs)))
    top = ranked[0].posterior if ranked else 0.0
    second = max(ranked[1].posterior if len(ranked) > 1 else 0.0, latent_probability)
    top_gap = float(max(0.0, top - second))
    distinguishability = float(min(1.0, top_gap / max(top, 1e-9)))
    if latent_probability > max(top, 0.45):
        decision = "latent_source"
    elif entropy > 0.88 or top < 0.18:
        decision = "inconclusive"
    elif distinguishability < 0.18:
        decision = "not_distinguishable"
    elif top > 0.55 and distinguishability > 0.35:
        decision = "strong_lead"
    else:
        decision = "weak_lead"
    return Attribution(
        candidates=ranked,
        latent_probability=latent_probability,
        posterior_entropy=entropy,
        top_gap=top_gap,
        distinguishability=distinguishability,
        decision_state=decision,
    )
