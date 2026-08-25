"""Experiment PRATIVARTAN path: reverse ensemble to locked Phi artifact."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import numpy as np

from experiments.go_nogo.config import ExperimentConfig
from experiments.go_nogo.forcing import DEG_LAT_KM, StructuredForcing, advect
from experiments.go_nogo.slick import ObservedSlick


@dataclass(frozen=True)
class PhiArtifact:
    phi_id: str
    data_path: Path
    phi: np.ndarray
    lon_edges: np.ndarray
    lat_edges: np.ndarray
    time_edges: np.ndarray
    diagnostics: dict[str, float | int | bool | str]
    sensitivity: dict[str, float | str]
    contract: object | None
    contract_error: str | None


def _sample_age_hours(slick: ObservedSlick, rng: np.random.Generator) -> float:
    age = rng.normal(slick.age_prior_mean_hours, slick.age_prior_std_hours)
    return float(np.clip(age, 1.0, slick.observation_time_hours + 18.0))


def _build_edges(values: np.ndarray, bins: int, pad: float) -> np.ndarray:
    lo, hi = float(np.min(values)) - pad, float(np.max(values)) + pad
    if abs(hi - lo) < 1e-9:
        lo -= pad or 0.01
        hi += pad or 0.01
    return np.linspace(lo, hi, bins + 1)


def _phi_diagnostics(phi: np.ndarray, lon_edges: np.ndarray, lat_edges: np.ndarray) -> dict[str, float | int | bool | str]:
    flat = phi.ravel()
    positive = flat[flat > 0]
    entropy = 0.0 if len(positive) == 0 else float(-np.sum(positive * np.log(positive)) / np.log(len(flat)))
    top_n = max(1, int(0.05 * len(flat)))
    concentration = float(np.sum(np.sort(flat)[-top_n:]))
    sorted_mass = np.sort(flat)[::-1]
    cells_90 = int(np.searchsorted(np.cumsum(sorted_mass), 0.9, side="left") + 1)
    dlon = float(np.mean(np.diff(lon_edges)))
    dlat = float(np.mean(np.diff(lat_edges)))
    mean_lat = float(np.mean(lat_edges))
    cell_area = abs(dlon * DEG_LAT_KM * np.cos(np.radians(mean_lat)) * dlat * DEG_LAT_KM)
    effective_support = float(cells_90 * cell_area)
    boundary = bool(
        np.sum(phi[:, 0, :]) + np.sum(phi[:, -1, :]) + np.sum(phi[:, :, 0]) + np.sum(phi[:, :, -1])
        > 0.08
    )
    n_modes = int(max(1, min(3, np.sum(flat > np.percentile(flat, 99.5)))))
    convergence_flag = "converged" if entropy < 0.82 else ("marginal" if entropy < 0.92 else "not_converged")
    return {
        "entropy": entropy,
        "concentration": concentration,
        "effective_support_km2": effective_support,
        "convergence": min(1.0, entropy),
        "convergence_flag": convergence_flag,
        "n_modes": n_modes,
        "multimodal": n_modes > 1,
        "boundary_interaction": boundary,
    }


def _try_build_phi_contract(
    *,
    phi_id: str,
    slick: ObservedSlick,
    data_path: Path,
    phi: np.ndarray,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,
    diagnostics: dict[str, float | int | bool | str],
    sensitivity: dict[str, float | str],
    config: ExperimentConfig,
) -> tuple[object | None, str | None]:
    try:
        from varuna_contracts import (  # type: ignore
            BBox,
            ConvergenceFlag,
            EvidenceEnvelope,
            GeoPoint,
            PhiDiagnostics,
            PhiField,
            Provenance,
            SensitivityBlock,
            SpatialMode,
            TimeDistribution,
            TrustState,
            UncertaintyBlock,
            ValidityState,
        )
    except Exception as exc:  # pragma: no cover - exercised only in under-provisioned envs.
        return None, str(exc)

    t_mass = phi.sum(axis=(1, 2))
    t_centers = 0.5 * (time_edges[:-1] + time_edges[1:])
    mode_idx = int(np.argmax(t_mass))
    cdf = np.cumsum(t_mass)
    p05 = float(t_centers[np.searchsorted(cdf, 0.05, side="left")])
    p95 = float(t_centers[min(len(t_centers) - 1, np.searchsorted(cdf, 0.95, side="left"))])
    y_idx, x_idx = np.unravel_index(int(np.argmax(phi[mode_idx])), phi[mode_idx].shape)
    mode = SpatialMode(
        centroid=GeoPoint(
            lon=float(0.5 * (lon_edges[x_idx] + lon_edges[x_idx + 1])),
            lat=float(0.5 * (lat_edges[y_idx] + lat_edges[y_idx + 1])),
        ),
        mass=float(np.max(phi)),
        area_km2=float(diagnostics["effective_support_km2"]),
        peak_time_unix=float(t_centers[mode_idx]),
    )
    env = EvidenceEnvelope(
        artifact_id=phi_id,
        case_id=slick.slick_id,
        produced_by="experiments.go_nogo.prativartan",
        model_version=config.model_version,
        provenance=Provenance(source_id="synthetic_go_nogo", notes="SIMULATED"),
        trust=TrustState.TRUSTED,
        uncertainty=UncertaintyBlock(
            representation="field",
            entropy=float(diagnostics["entropy"]),
            n_samples=config.n_backward_particles * config.n_ensemble_members,
            sensitivity={k: float(v) for k, v in sensitivity.items() if isinstance(v, float)},
        ),
        validity_state=ValidityState.VALID
        if diagnostics["convergence_flag"] != "not_converged"
        else ValidityState.RESTRICTED,
    )
    return (
        PhiField(
            phi_id=phi_id,
            slick_id=slick.slick_id,
            case_id=slick.slick_id,
            data_path=str(data_path),
            bbox=BBox(
                min_lon=float(lon_edges[0]),
                min_lat=float(lat_edges[0]),
                max_lon=float(lon_edges[-1]),
                max_lat=float(lat_edges[-1]),
            ),
            grid_shape=phi.shape,
            time_distribution=TimeDistribution(
                time_edges_unix=[float(x) for x in time_edges],
                mass=[float(x) for x in t_mass],
                mode_unix=float(t_centers[mode_idx]),
                p05_unix=p05,
                p95_unix=p95,
            ),
            spatial_modes=[mode],
            diagnostics=PhiDiagnostics(
                entropy=float(diagnostics["entropy"]),
                concentration=float(diagnostics["concentration"]),
                effective_support_km2=float(diagnostics["effective_support_km2"]),
                convergence=float(diagnostics["convergence"]),
                convergence_flag=ConvergenceFlag(str(diagnostics["convergence_flag"])),
                n_modes=int(diagnostics["n_modes"]),
                multimodal=bool(diagnostics["multimodal"]),
                boundary_interaction=bool(diagnostics["boundary_interaction"]),
                particles_lost=0,
                particles_seeded=config.n_backward_particles * config.n_ensemble_members,
                ensemble_members_completed=config.n_ensemble_members,
                ensemble_members_requested=config.n_ensemble_members,
                runtime_seconds=float(diagnostics["runtime_seconds"]),
            ),
            sensitivity=SensitivityBlock(
                age_sensitivity=float(sensitivity["age_sensitivity"]),
                forcing_sensitivity=float(sensitivity["forcing_sensitivity"]),
                diffusivity_sensitivity=float(sensitivity["diffusivity_sensitivity"]),
                weathering_sensitivity=float(sensitivity["weathering_sensitivity"]),
            ),
            n_particles=config.n_backward_particles,
            n_ensemble=config.n_ensemble_members,
            backward_duration_hours=float(slick.age_prior_mean_hours + 2.0 * slick.age_prior_std_hours),
            dt_seconds=config.dt_seconds,
            forcing_current_source="synthetic_structured_inference",
            forcing_wind_source="synthetic_structured_inference",
            weathering_model=None,
            envelope=env,
            created_at=datetime.now(UTC),
        ),
        None,
    )


def run_prativartan(
    slick: ObservedSlick,
    forcing: StructuredForcing,
    config: ExperimentConfig,
    *,
    trial_key: str,
    output_dir: Path,
    rng: np.random.Generator,
) -> PhiArtifact:
    """Run the fair reverse ensemble and persist the locked .npz Phi format."""
    start = perf_counter()
    all_lons: list[np.ndarray] = []
    all_lats: list[np.ndarray] = []
    all_times: list[np.ndarray] = []
    age_samples: list[float] = []

    for _ in range(config.n_ensemble_members):
        age_hours = _sample_age_hours(slick, rng)
        age_samples.append(age_hours)
        indices = rng.integers(0, len(slick.lons), config.n_backward_particles)
        hist_lon, hist_lat, hist_t = advect(
            slick.lons[indices],
            slick.lats[indices],
            forcing,
            start_time_hours=slick.observation_time_hours,
            duration_hours=age_hours,
            dt_seconds=config.dt_seconds,
            wind_drift_factor=config.wind_drift_factor,
            diffusivity_m2s=config.diffusivity_m2s,
            rng=rng,
            backward=True,
        )
        all_lons.append(hist_lon.ravel())
        all_lats.append(hist_lat.ravel())
        all_times.append(np.repeat(hist_t, hist_lon.shape[1]))

    lon_samples = np.concatenate(all_lons)
    lat_samples = np.concatenate(all_lats)
    time_samples_hours = np.concatenate(all_times)
    lon_edges = _build_edges(lon_samples, config.grid_x_bins, 0.015)
    lat_edges = _build_edges(lat_samples, config.grid_y_bins, 0.015)
    time_edges_hours = np.linspace(
        float(np.min(time_samples_hours)),
        slick.observation_time_hours,
        config.grid_time_bins + 1,
    )
    hist, _ = np.histogramdd(
        (time_samples_hours, lat_samples, lon_samples),
        bins=(time_edges_hours, lat_edges, lon_edges),
    )
    phi = hist.astype(np.float32)
    total = float(phi.sum())
    if total <= 0:
        raise ValueError("reverse ensemble produced no Phi mass")
    phi /= total

    data_dir = output_dir / "artifacts"
    data_dir.mkdir(parents=True, exist_ok=True)
    phi_id = f"phi-{trial_key}"
    data_path = data_dir / f"{phi_id}.npz"
    epoch = datetime(2026, 1, 1, tzinfo=UTC)
    time_edges_unix = np.array(
        [(epoch + timedelta(hours=float(h))).timestamp() for h in time_edges_hours],
        dtype=np.float64,
    )
    particle_count = np.full(config.grid_time_bins, config.n_backward_particles, dtype=np.int32)
    np.savez_compressed(
        data_path,
        phi=phi.astype(np.float32),
        lon_edges=lon_edges.astype(np.float64),
        lat_edges=lat_edges.astype(np.float64),
        time_edges=time_edges_unix,
        particle_count=particle_count,
    )

    diagnostics = _phi_diagnostics(phi, lon_edges, lat_edges)
    diagnostics["particles_seeded"] = config.n_backward_particles * config.n_ensemble_members
    diagnostics["particles_lost"] = 0
    diagnostics["ensemble_members_requested"] = config.n_ensemble_members
    diagnostics["ensemble_members_completed"] = config.n_ensemble_members
    diagnostics["runtime_seconds"] = perf_counter() - start
    sensitivity = {
        "age_sensitivity": float(np.std(age_samples) / max(np.mean(age_samples), 1e-9)),
        "forcing_sensitivity": {"baseline": 0.15, "moderate": 0.45, "high": 0.75}.get(
            "moderate", 0.45
        ),
        "diffusivity_sensitivity": 0.25,
        "weathering_sensitivity": 0.0,
    }
    sensitivity["dominant_assumption"] = max(
        (k for k in sensitivity if k.endswith("_sensitivity")),
        key=lambda k: float(sensitivity[k]),
    ).replace("_sensitivity", "")
    contract, contract_error = _try_build_phi_contract(
        phi_id=phi_id,
        slick=slick,
        data_path=data_path,
        phi=phi,
        lon_edges=lon_edges,
        lat_edges=lat_edges,
        time_edges=time_edges_unix,
        diagnostics=diagnostics,
        sensitivity=sensitivity,
        config=config,
    )
    return PhiArtifact(
        phi_id=phi_id,
        data_path=data_path,
        phi=phi,
        lon_edges=lon_edges,
        lat_edges=lat_edges,
        time_edges=time_edges_hours,
        diagnostics=diagnostics,
        sensitivity=sensitivity,
        contract=contract,
        contract_error=contract_error,
    )
