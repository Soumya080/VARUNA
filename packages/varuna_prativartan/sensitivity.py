"""
VARUNA GRID — Φ sensitivity sweep mechanics (ADR-0007).

Implements the MECHANICAL half of the sensitivity sweep only: real ensemble
re-runs at perturbed age/forcing parameters, and real measured differences
between the resulting fields. It does NOT populate `SensitivityBlock` — the
conversion from these raw measurements into the `[0,1]` radius-normalized
scalar that contract requires is an open scientific decision (see
ADR-0007's "one genuinely open decision" section), not something to guess
here.

Every perturbation genuinely re-runs `run_backward_ensemble` and
`build_phi_field` — engine.py's advection mathematics are completely
untouched. Nothing here perturbs an already-computed Phi, adds synthetic
noise to a result, or relabels one run as several.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from varuna_contracts.evidence import EvidenceEnvelope
from varuna_contracts.phi import ConvergenceFlag, PhiField
from varuna_prativartan.config import PratiConfig
from varuna_prativartan.current_field import AbstractCurrentField, AbstractWindField
from varuna_prativartan.ensemble import run_backward_ensemble
from varuna_prativartan.phi_builder import build_phi_field


@dataclass(frozen=True)
class PerturbationRunResult:
    """One real ensemble run at a specific parameter setting."""
    label: str  # "baseline" | "age_minus" | "age_plus" | "forcing_minus" | "forcing_plus"
    phi: PhiField
    centroid_lon: float
    centroid_lat: float


@dataclass(frozen=True)
class SensitivitySweepResult:
    """
    Raw measured differences between perturbed runs and the shared
    baseline. Deliberately NOT a `SensitivityBlock` — see module docstring.
    """
    baseline: PerturbationRunResult
    age_minus: PerturbationRunResult
    age_plus: PerturbationRunResult
    forcing_minus: PerturbationRunResult
    forcing_plus: PerturbationRunResult

    age_centroid_shift_km: float
    forcing_centroid_shift_km: float
    age_n_modes_delta: dict[str, int] = field(default_factory=dict)
    forcing_n_modes_delta: dict[str, int] = field(default_factory=dict)
    age_convergence_flag_changed: bool = False
    forcing_convergence_flag_changed: bool = False
    age_ensemble_completeness_delta: dict[str, float] = field(default_factory=dict)
    forcing_ensemble_completeness_delta: dict[str, float] = field(default_factory=dict)


def _spatial_centroid(phi: PhiField) -> tuple[float, float]:
    """Mass-weighted (lon, lat) centroid of the field's spatial marginal,
    read from the actual built .npz — not re-derived from raw particles."""
    npz = np.load(phi.data_path)
    phi_array = npz["phi"]  # (n_t, n_y, n_x)
    lon_edges = npz["lon_edges"]
    lat_edges = npz["lat_edges"]
    lon_centers = 0.5 * (lon_edges[:-1] + lon_edges[1:])
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])

    spatial = phi_array.sum(axis=0)  # (n_y, n_x)
    total = spatial.sum()
    if total <= 0:
        return float(lon_centers.mean()), float(lat_centers.mean())
    lon_mass = spatial.sum(axis=0)  # sum over y -> (n_x,)
    lat_mass = spatial.sum(axis=1)  # sum over x -> (n_y,)
    centroid_lon = float((lon_centers * lon_mass).sum() / total)
    centroid_lat = float((lat_centers * lat_mass).sum() / total)
    return centroid_lon, centroid_lat


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return float(2 * R * np.arcsin(np.sqrt(a)))


def _run(
    *, label: str,
    slick_lons: np.ndarray, slick_lats: np.ndarray, obs_time_hours: float,
    case_id: str, slick_id: str,
    age_prior_mean_hours: float, age_prior_std_hours: float,
    config: PratiConfig,
    current: AbstractCurrentField, wind: AbstractWindField,
    input_envelope: EvidenceEnvelope,
) -> PerturbationRunResult:
    import time
    t0 = time.perf_counter()
    ensemble_res = run_backward_ensemble(
        obs_lons=slick_lons, obs_lats=slick_lats, obs_time_hours=obs_time_hours,
        current=current, wind=wind, config=config,
    )
    runtime_seconds = time.perf_counter() - t0
    phi = build_phi_field(
        ensemble_results=ensemble_res,
        case_id=case_id, slick_id=f"{slick_id}-{label}",
        input_envelope=input_envelope,
        obs_time_hours=obs_time_hours,
        age_prior_mean_hours=age_prior_mean_hours,
        age_prior_std_hours=age_prior_std_hours,
        config=config,
        runtime_seconds=runtime_seconds,
    )
    lon_c, lat_c = _spatial_centroid(phi)
    return PerturbationRunResult(label=label, phi=phi, centroid_lon=lon_c, centroid_lat=lat_c)


def run_sensitivity_sweep(
    *,
    slick_lons: np.ndarray,
    slick_lats: np.ndarray,
    obs_time_hours: float,
    case_id: str,
    slick_id: str,
    age_prior_mean_hours: float,
    age_prior_std_hours: float,
    config: PratiConfig,
    current: AbstractCurrentField,
    wind: AbstractWindField,
    input_envelope: EvidenceEnvelope,
) -> SensitivitySweepResult:
    """
    Real re-execution of the ensemble at 5 parameter settings (1 baseline +
    2 age + 2 forcing). Age axis perturbs `age_prior_mean_hours` by
    `± age_prior_std_hours` — the existing, already-supplied 1-sigma age
    uncertainty (ADR-0007), holding forcing config fixed. Forcing axis
    perturbs `PratiConfig.current_noise_range` to its own existing low/high
    bounds pinned (rather than randomly resampled per member, which is what
    the unperturbed ensemble already does) — also an existing range, not a
    new one — holding age fixed at baseline.

    `current`/`wind` are shared unmodified across all 5 runs; only
    `config`/`age_prior_mean_hours` differ per run. `config.seed` is held
    fixed across all 5 runs so any difference in output is attributable to
    the perturbation, not to a different random draw.
    """
    common = dict(
        slick_lons=slick_lons, slick_lats=slick_lats, obs_time_hours=obs_time_hours,
        case_id=case_id, slick_id=slick_id, current=current, wind=wind,
        input_envelope=input_envelope,
    )

    baseline = _run(
        label="baseline", age_prior_mean_hours=age_prior_mean_hours,
        age_prior_std_hours=age_prior_std_hours, config=config, **common,
    )

    age_minus = _run(
        label="age_minus",
        age_prior_mean_hours=age_prior_mean_hours - age_prior_std_hours,
        age_prior_std_hours=age_prior_std_hours, config=config, **common,
    )
    age_plus = _run(
        label="age_plus",
        age_prior_mean_hours=age_prior_mean_hours + age_prior_std_hours,
        age_prior_std_hours=age_prior_std_hours, config=config, **common,
    )

    cnf_lo, cnf_hi = config.current_noise_range
    config_forcing_minus = copy.deepcopy(config)
    config_forcing_minus.current_noise_range = (cnf_lo, cnf_lo)
    config_forcing_plus = copy.deepcopy(config)
    config_forcing_plus.current_noise_range = (cnf_hi, cnf_hi)

    forcing_minus = _run(
        label="forcing_minus", age_prior_mean_hours=age_prior_mean_hours,
        age_prior_std_hours=age_prior_std_hours, config=config_forcing_minus, **common,
    )
    forcing_plus = _run(
        label="forcing_plus", age_prior_mean_hours=age_prior_mean_hours,
        age_prior_std_hours=age_prior_std_hours, config=config_forcing_plus, **common,
    )

    age_shift = max(
        _haversine_km(baseline.centroid_lon, baseline.centroid_lat, age_minus.centroid_lon, age_minus.centroid_lat),
        _haversine_km(baseline.centroid_lon, baseline.centroid_lat, age_plus.centroid_lon, age_plus.centroid_lat),
    )
    forcing_shift = max(
        _haversine_km(baseline.centroid_lon, baseline.centroid_lat, forcing_minus.centroid_lon, forcing_minus.centroid_lat),
        _haversine_km(baseline.centroid_lon, baseline.centroid_lat, forcing_plus.centroid_lon, forcing_plus.centroid_lat),
    )

    def _flag_changed(a: ConvergenceFlag, b: ConvergenceFlag) -> bool:
        return a != b

    return SensitivitySweepResult(
        baseline=baseline, age_minus=age_minus, age_plus=age_plus,
        forcing_minus=forcing_minus, forcing_plus=forcing_plus,
        age_centroid_shift_km=age_shift,
        forcing_centroid_shift_km=forcing_shift,
        age_n_modes_delta={
            "age_minus": age_minus.phi.diagnostics.n_modes - baseline.phi.diagnostics.n_modes,
            "age_plus": age_plus.phi.diagnostics.n_modes - baseline.phi.diagnostics.n_modes,
        },
        forcing_n_modes_delta={
            "forcing_minus": forcing_minus.phi.diagnostics.n_modes - baseline.phi.diagnostics.n_modes,
            "forcing_plus": forcing_plus.phi.diagnostics.n_modes - baseline.phi.diagnostics.n_modes,
        },
        age_convergence_flag_changed=(
            _flag_changed(baseline.phi.diagnostics.convergence_flag, age_minus.phi.diagnostics.convergence_flag)
            or _flag_changed(baseline.phi.diagnostics.convergence_flag, age_plus.phi.diagnostics.convergence_flag)
        ),
        forcing_convergence_flag_changed=(
            _flag_changed(baseline.phi.diagnostics.convergence_flag, forcing_minus.phi.diagnostics.convergence_flag)
            or _flag_changed(baseline.phi.diagnostics.convergence_flag, forcing_plus.phi.diagnostics.convergence_flag)
        ),
        age_ensemble_completeness_delta={
            "age_minus": age_minus.phi.diagnostics.ensemble_completeness - baseline.phi.diagnostics.ensemble_completeness,
            "age_plus": age_plus.phi.diagnostics.ensemble_completeness - baseline.phi.diagnostics.ensemble_completeness,
        },
        forcing_ensemble_completeness_delta={
            "forcing_minus": forcing_minus.phi.diagnostics.ensemble_completeness - baseline.phi.diagnostics.ensemble_completeness,
            "forcing_plus": forcing_plus.phi.diagnostics.ensemble_completeness - baseline.phi.diagnostics.ensemble_completeness,
        },
    )
