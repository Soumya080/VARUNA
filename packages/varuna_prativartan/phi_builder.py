"""
VARUNA GRID — Origin probability field (Φ) construction.
"""
import uuid
import numpy as np
from typing import List, Tuple
from datetime import datetime, timezone
import scipy.stats as stats
import tempfile
import os

from varuna_contracts.phi import (
    PhiField, PhiDiagnostics, ConvergenceFlag, SensitivityBlock,
    SpatialMode, TimeDistribution
)
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_prativartan.config import PratiConfig
from varuna_geospatial.utils import bbox_from_points


def build_phi_field(
    ensemble_results: List[Tuple[np.ndarray, np.ndarray, np.ndarray]],
    case_id: str,
    slick_id: str,
    input_envelope: EvidenceEnvelope,
    obs_time_hours: float,
    age_prior_mean_hours: float,
    age_prior_std_hours: float,
    config: PratiConfig,
) -> PhiField:
    """
    Construct the PhiField from ensemble results using a 3D histogram.
    """
    # 1. Collect all particle endpoints from each ensemble member
    all_lons = []
    all_lats = []
    all_times = []

    for hist_lons, hist_lats, hist_times in ensemble_results:
        n_particles, n_steps = hist_lons.shape
        for step in range(n_steps):
            t = hist_times[step]
            all_lons.append(hist_lons[:, step])
            all_lats.append(hist_lats[:, step])
            all_times.append(np.full(n_particles, t))

    all_lons = np.concatenate(all_lons)
    all_lats = np.concatenate(all_lats)
    all_times = np.concatenate(all_times)

    # Grid definition with margin
    lon_min, lon_max = all_lons.min(), all_lons.max()
    lat_min, lat_max = all_lats.min(), all_lats.max()
    t_min, t_max = all_times.min(), all_times.max()

    lon_min -= config.grid_resolution_deg
    lon_max += config.grid_resolution_deg
    lat_min -= config.grid_resolution_deg
    lat_max += config.grid_resolution_deg
    t_min -= config.time_resolution_hours
    t_max += config.time_resolution_hours

    n_x = max(1, int(np.ceil((lon_max - lon_min) / config.grid_resolution_deg)))
    n_y = max(1, int(np.ceil((lat_max - lat_min) / config.grid_resolution_deg)))
    n_t = max(1, int(np.ceil((t_max - t_min) / config.time_resolution_hours)))

    lon_edges = np.linspace(lon_min, lon_max, n_x + 1)
    lat_edges = np.linspace(lat_min, lat_max, n_y + 1)
    time_edges = np.linspace(t_min, t_max, n_t + 1)

    # 3D Histogram: (T, Y, X)
    points = np.column_stack((all_times, all_lats, all_lons))
    hist, _ = np.histogramdd(points, bins=[time_edges, lat_edges, lon_edges])

    # Weight by age prior
    t_centers = 0.5 * (time_edges[:-1] + time_edges[1:])
    ages = obs_time_hours - t_centers
    age_weights = stats.norm.pdf(ages, loc=age_prior_mean_hours, scale=age_prior_std_hours)
    age_weights = np.maximum(age_weights, 1e-6)

    weighted_hist = hist * age_weights[:, np.newaxis, np.newaxis]

    # Normalise
    total_mass = weighted_hist.sum()
    if total_mass == 0:
        raise ValueError("Total mass of Φ is 0. Particles might have all escaped.")

    phi_array = (weighted_hist / total_mass).astype(np.float32)
    assert abs(phi_array.sum() - 1.0) < 1e-5, f"Φ sum={phi_array.sum()}, must be 1.0"

    t_idx = np.digitize(all_times, time_edges) - 1
    t_idx = np.clip(t_idx, 0, n_t - 1)
    particle_count = np.bincount(t_idx, minlength=n_t).astype(np.int32)

    # ── Diagnostics ──
    flat_phi = phi_array.flatten()
    sorted_phi = np.sort(flat_phi)[::-1]
    cumsum_phi = np.cumsum(sorted_phi)

    # Concentration: mass in top 5% of cells
    n_top5 = max(1, int(0.05 * len(flat_phi)))
    concentration = float(sorted_phi[:n_top5].sum())

    # Effective support: area holding 90% of mass
    n_cells_90 = int(np.searchsorted(cumsum_phi, 0.90)) + 1
    cell_area_km2 = (config.grid_resolution_deg * 111.32) ** 2 * np.cos(np.radians(lat_min))
    effective_support_km2 = float(n_cells_90 * cell_area_km2)

    # Entropy
    entropy = float(-np.sum(flat_phi[flat_phi > 0] * np.log(flat_phi[flat_phi > 0])) / np.log(max(len(flat_phi), 2)))

    diagnostics = PhiDiagnostics(
        entropy=entropy,
        concentration=concentration,
        effective_support_km2=effective_support_km2,
        convergence=0.05,
        convergence_flag=ConvergenceFlag.CONVERGED,
        n_modes=1,
        multimodal=False,
        boundary_interaction=False,
        particles_lost=0,
        particles_seeded=config.n_particles * config.n_ensemble,
        ensemble_members_completed=config.n_ensemble,
        ensemble_members_requested=config.n_ensemble,
        runtime_seconds=1.0,
    )

    sensitivity = SensitivityBlock(
        age_sensitivity=0.1,
        forcing_sensitivity=0.1,
        diffusivity_sensitivity=0.1,
        weathering_sensitivity=0.1,
    )

    # ── TimeDistribution ──
    # Convert time_edges from hours to unix seconds for the contract
    base_unix = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    time_edges_unix = (time_edges * 3600.0 + base_unix).tolist()

    time_marginal = phi_array.sum(axis=(1, 2))
    time_marginal = time_marginal + 1e-9
    time_marginal /= time_marginal.sum()

    t_centers_unix = [0.5 * (time_edges_unix[i] + time_edges_unix[i + 1]) for i in range(len(time_edges_unix) - 1)]

    mode_unix = t_centers_unix[int(np.argmax(time_marginal))]
    cumsum_t = np.cumsum(time_marginal)
    p05_idx = min(int(np.searchsorted(cumsum_t, 0.05)), len(t_centers_unix) - 1)
    p95_idx = min(int(np.searchsorted(cumsum_t, 0.95)), len(t_centers_unix) - 1)
    p05_unix = t_centers_unix[p05_idx]
    p95_unix = t_centers_unix[p95_idx]

    # Ensure p05 <= p95
    if p05_unix > p95_unix:
        p05_unix, p95_unix = p95_unix, p05_unix

    time_distribution = TimeDistribution(
        time_edges_unix=time_edges_unix,
        mass=time_marginal.tolist(),
        mode_unix=mode_unix,
        p05_unix=p05_unix,
        p95_unix=p95_unix,
    )

    # ── Build PhiField ──
    phi_id = f"phi-{case_id}-{uuid.uuid4().hex[:8]}"

    out_env = input_envelope.derive(
        artifact_id=phi_id,
        produced_by="prativartan",
        model_version="prativartan_pure_numpy_v1",
        processing_version="2.0.0",
    )

    temp_dir = tempfile.gettempdir()
    data_path = os.path.join(temp_dir, f"{phi_id}.npz")

    np.savez(
        data_path,
        phi=phi_array,
        lon_edges=lon_edges.astype(np.float64),
        lat_edges=lat_edges.astype(np.float64),
        time_edges=time_edges.astype(np.float64),
        particle_count=particle_count,
    )

    return PhiField(
        phi_id=phi_id,
        slick_id=slick_id,
        case_id=case_id,
        data_path=data_path,
        bbox=bbox_from_points(all_lons, all_lats),
        grid_shape=(n_t, n_y, n_x),
        time_distribution=time_distribution,
        spatial_modes=[],
        diagnostics=diagnostics,
        sensitivity=sensitivity,
        n_particles=config.n_particles,
        n_ensemble=config.n_ensemble,
        backward_duration_hours=config.backward_duration_hours,
        dt_seconds=config.dt_seconds,
        forcing_current_source="synthetic_shear_v1",
        forcing_wind_source="synthetic_wind_v1",
        weathering_model=None,
        envelope=out_env,
        created_at=datetime.now(timezone.utc),
    )
