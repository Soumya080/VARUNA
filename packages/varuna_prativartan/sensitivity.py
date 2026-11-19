"""
VARUNA GRID — Φ sensitivity sweep: mechanics AND normalization (ADR-0007).

Re-runs the real ensemble at perturbed age/forcing/diffusivity parameters
(never perturbing an already-computed Phi, never adding synthetic noise to
a result) and converts the measured differences into the `SensitivityBlock`
contract's `[0, ...)` displacement scale.

Three of the four SensitivityBlock scores are populated for real:
age_sensitivity, forcing_sensitivity, diffusivity_sensitivity. The fourth,
weathering_sensitivity, has no model to perturb at all — PhiField.
weathering_model is always None in this codebase — and is honestly None
(see ADR-0007's amendment making that field Optional), never a fabricated
number standing in for physics that does not exist here.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np

from varuna_contracts.evidence import EvidenceEnvelope
from varuna_contracts.phi import ConvergenceFlag, PhiField, SensitivityBlock
from varuna_prativartan.config import PratiConfig
from varuna_prativartan.current_field import AbstractCurrentField, AbstractWindField
from varuna_prativartan.ensemble import run_backward_ensemble
from varuna_prativartan.phi_builder import build_phi_field


@dataclass(frozen=True)
class PerturbationRunResult:
    """One real ensemble run at a specific parameter setting."""
    label: str
    phi: PhiField
    centroid_lon: float
    centroid_lat: float


@dataclass(frozen=True)
class SensitivitySweepResult:
    """
    Raw measured differences between perturbed runs and the shared
    baseline, for all three swept axes (age, forcing, diffusivity).
    """
    baseline: PerturbationRunResult
    age_minus: PerturbationRunResult
    age_plus: PerturbationRunResult
    forcing_minus: PerturbationRunResult
    forcing_plus: PerturbationRunResult
    diffusivity_minus: PerturbationRunResult
    diffusivity_plus: PerturbationRunResult

    age_centroid_shift_km: float
    forcing_centroid_shift_km: float
    diffusivity_centroid_shift_km: float

    age_n_modes_delta: dict[str, int] = field(default_factory=dict)
    forcing_n_modes_delta: dict[str, int] = field(default_factory=dict)
    diffusivity_n_modes_delta: dict[str, int] = field(default_factory=dict)
    age_convergence_flag_changed: bool = False
    forcing_convergence_flag_changed: bool = False
    diffusivity_convergence_flag_changed: bool = False
    age_ensemble_completeness_delta: dict[str, float] = field(default_factory=dict)
    forcing_ensemble_completeness_delta: dict[str, float] = field(default_factory=dict)
    diffusivity_ensemble_completeness_delta: dict[str, float] = field(default_factory=dict)


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
    lon_mass = spatial.sum(axis=0)
    lat_mass = spatial.sum(axis=1)
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
    Real re-execution of the ensemble at 7 parameter settings (1 baseline +
    2 age + 2 forcing + 2 diffusivity). Age perturbs `age_prior_mean_hours`
    by `± age_prior_std_hours` — the existing, already-supplied 1-sigma age
    uncertainty. Forcing pins `PratiConfig.current_noise_range` to its own
    existing low/high bounds (rather than randomly resampled per member).
    Diffusivity pins `PratiConfig.diffusivity_range` to its own existing
    low/high bounds, the same treatment as forcing. All three ranges
    pre-existed this change (ADR-0007) — none is invented here.

    `config.seed` is held fixed across all 7 runs so any difference in
    output is attributable to the perturbation, not to a different random
    draw.
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

    diff_lo, diff_hi = config.diffusivity_range
    config_diff_minus = copy.deepcopy(config)
    config_diff_minus.diffusivity_range = (diff_lo, diff_lo)
    config_diff_plus = copy.deepcopy(config)
    config_diff_plus.diffusivity_range = (diff_hi, diff_hi)

    diffusivity_minus = _run(
        label="diffusivity_minus", age_prior_mean_hours=age_prior_mean_hours,
        age_prior_std_hours=age_prior_std_hours, config=config_diff_minus, **common,
    )
    diffusivity_plus = _run(
        label="diffusivity_plus", age_prior_mean_hours=age_prior_mean_hours,
        age_prior_std_hours=age_prior_std_hours, config=config_diff_plus, **common,
    )

    def _shift(a: PerturbationRunResult, b: PerturbationRunResult) -> float:
        return _haversine_km(a.centroid_lon, a.centroid_lat, b.centroid_lon, b.centroid_lat)

    def _flag_changed(a: ConvergenceFlag, b: ConvergenceFlag) -> bool:
        return a != b

    age_shift = max(_shift(baseline, age_minus), _shift(baseline, age_plus))
    forcing_shift = max(_shift(baseline, forcing_minus), _shift(baseline, forcing_plus))
    diffusivity_shift = max(_shift(baseline, diffusivity_minus), _shift(baseline, diffusivity_plus))

    def _n_modes_delta(minus: PerturbationRunResult, plus: PerturbationRunResult, minus_key: str, plus_key: str) -> dict[str, int]:
        return {
            minus_key: minus.phi.diagnostics.n_modes - baseline.phi.diagnostics.n_modes,
            plus_key: plus.phi.diagnostics.n_modes - baseline.phi.diagnostics.n_modes,
        }

    def _completeness_delta(minus: PerturbationRunResult, plus: PerturbationRunResult, minus_key: str, plus_key: str) -> dict[str, float]:
        return {
            minus_key: minus.phi.diagnostics.ensemble_completeness - baseline.phi.diagnostics.ensemble_completeness,
            plus_key: plus.phi.diagnostics.ensemble_completeness - baseline.phi.diagnostics.ensemble_completeness,
        }

    return SensitivitySweepResult(
        baseline=baseline, age_minus=age_minus, age_plus=age_plus,
        forcing_minus=forcing_minus, forcing_plus=forcing_plus,
        diffusivity_minus=diffusivity_minus, diffusivity_plus=diffusivity_plus,
        age_centroid_shift_km=age_shift,
        forcing_centroid_shift_km=forcing_shift,
        diffusivity_centroid_shift_km=diffusivity_shift,
        age_n_modes_delta=_n_modes_delta(age_minus, age_plus, "age_minus", "age_plus"),
        forcing_n_modes_delta=_n_modes_delta(forcing_minus, forcing_plus, "forcing_minus", "forcing_plus"),
        diffusivity_n_modes_delta=_n_modes_delta(diffusivity_minus, diffusivity_plus, "diffusivity_minus", "diffusivity_plus"),
        age_convergence_flag_changed=(
            _flag_changed(baseline.phi.diagnostics.convergence_flag, age_minus.phi.diagnostics.convergence_flag)
            or _flag_changed(baseline.phi.diagnostics.convergence_flag, age_plus.phi.diagnostics.convergence_flag)
        ),
        forcing_convergence_flag_changed=(
            _flag_changed(baseline.phi.diagnostics.convergence_flag, forcing_minus.phi.diagnostics.convergence_flag)
            or _flag_changed(baseline.phi.diagnostics.convergence_flag, forcing_plus.phi.diagnostics.convergence_flag)
        ),
        diffusivity_convergence_flag_changed=(
            _flag_changed(baseline.phi.diagnostics.convergence_flag, diffusivity_minus.phi.diagnostics.convergence_flag)
            or _flag_changed(baseline.phi.diagnostics.convergence_flag, diffusivity_plus.phi.diagnostics.convergence_flag)
        ),
        age_ensemble_completeness_delta=_completeness_delta(age_minus, age_plus, "age_minus", "age_plus"),
        forcing_ensemble_completeness_delta=_completeness_delta(forcing_minus, forcing_plus, "forcing_minus", "forcing_plus"),
        diffusivity_ensemble_completeness_delta=_completeness_delta(diffusivity_minus, diffusivity_plus, "diffusivity_minus", "diffusivity_plus"),
    )


def effective_radius_km(phi: PhiField) -> float:
    """
    Circular-equivalent radius of the field's own `effective_support_km2`
    (already-computed: "area holding 90% of mass"). This is the literal
    instantiation of SensitivityBlock's own docstring — "the field moves
    by its own effective radius" — via the standard area -> radius
    conversion for a circle (`r = sqrt(A / pi)`). `pi` is a geometric
    identity, not a tunable scientific assumption; there is no free
    parameter in this function.
    """
    area = phi.diagnostics.effective_support_km2
    if area <= 0:
        return 0.0
    return float(np.sqrt(area / np.pi))


def build_sensitivity_block(sweep: SensitivitySweepResult) -> SensitivityBlock:
    """
    ADR-0007 (ratified): convert the sweep's raw centroid shifts into
    SensitivityBlock's displacement scale by dividing each by the
    baseline field's own effective radius. A shift equal to the baseline
    field's own effective radius scores exactly 1.0, matching the
    contract's docstring precisely — not clipped to [0,1], since
    SensitivityBlock's fields only require `>= 0` (a shift larger than
    the field's own radius is a real, reportable, >1 sensitivity, not an
    error).

    weathering_sensitivity is not computed by this sweep — no weathering
    model exists in PRATIVARTAN (`PhiField.weathering_model` is always
    None) — and is honestly `None` (SensitivityBlock.weathering_sensitivity
    was widened to Optional in this same ADR amendment for exactly this
    reason).

    Raises ValueError if the baseline field's effective_support_km2 is
    zero — a degenerate field with no spatial spread has no radius to
    normalize against, and reporting a number in that case (0.0, or an
    unbounded ratio) would itself be a fabrication of the kind ADR-0006/
    0007 exist to prevent.
    """
    radius_km = effective_radius_km(sweep.baseline.phi)
    if radius_km <= 0:
        raise ValueError(
            "Cannot compute a radius-normalized sensitivity: the baseline "
            "Phi field's effective_support_km2 is 0 (a degenerate field "
            "with no spatial spread). Reporting a sensitivity score here "
            "would be a fabrication, not a measurement."
        )

    return SensitivityBlock(
        age_sensitivity=sweep.age_centroid_shift_km / radius_km,
        forcing_sensitivity=sweep.forcing_centroid_shift_km / radius_km,
        diffusivity_sensitivity=sweep.diffusivity_centroid_shift_km / radius_km,
        weathering_sensitivity=None,
    )
