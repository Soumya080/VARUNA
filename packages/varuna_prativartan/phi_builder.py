"""
VARUNA GRID — Origin probability field (Φ) construction.
"""
import uuid
import numpy as np
from typing import List, Tuple
from datetime import datetime, timezone
import scipy.stats as stats
import scipy.ndimage as ndimage
import tempfile
import os

from varuna_contracts.phi import (
    PhiField, PhiDiagnostics, ConvergenceFlag,
    SpatialMode, TimeDistribution
)
from varuna_contracts.evidence import EvidenceEnvelope
from varuna_prativartan.config import PratiConfig
from varuna_geospatial.utils import bbox_from_points

# Fraction of a cell's peak mass above which it counts toward a spatial mode
# / boundary-interaction check. Not a scientific threshold requiring an ADR
# (see PratiConfig.convergence_threshold for the one that is) — it is a
# structural-detection cutoff, the same kind of choice as a histogram bin
# count. Kept as a named constant rather than a config field because there is
# no evidence yet that it needs to be tuned per case.
_MODE_MASS_FRACTION = 0.10


def build_phi_field(
    ensemble_results: List[Tuple[np.ndarray, np.ndarray, np.ndarray]],
    case_id: str,
    slick_id: str,
    input_envelope: EvidenceEnvelope,
    obs_time_hours: float,
    age_prior_mean_hours: float,
    age_prior_std_hours: float,
    config: PratiConfig,
    runtime_seconds: float,
) -> PhiField:
    """
    Construct the PhiField from ensemble results using a 3D histogram.

    `runtime_seconds` is measured by the caller around its
    run_backward_ensemble(...) call (see PrativartanService.reconstruct_origin)
    — the ensemble has already finished by the time this function runs, so it
    cannot honestly measure its own wall-clock cost; it can only carry the
    real number through into PhiDiagnostics instead of the literal 1.0 that
    used to sit here unconditionally.
    """
    if not ensemble_results:
        raise ValueError(
            "ensemble_results is empty — every ensemble member failed "
            "(see ensemble.py warnings). Cannot build a Phi field with zero "
            "completed members."
        )

    # ── Honest particle-count accounting, before anything else ──
    # PhiField.n_particles must report what was actually advected, not the
    # requested config value: run_backward_ensemble() draws
    # min(config.n_particles, n_obs) particles per member, so a seed with
    # fewer observation points than config.n_particles silently caps below
    # the requested count with nothing to say so (found in this same pass —
    # both this session and a parallel one hit it independently against a
    # too-small placeholder). Every member is sampled from the same
    # config.n_particles/n_obs decision, so their per-member counts must
    # all agree; that is asserted, not assumed, so a real disagreement
    # raises instead of silently picking one member's count.
    per_member_counts = {hist_lons.shape[0] for hist_lons, _, _ in ensemble_results}
    if len(per_member_counts) != 1:
        raise ValueError(
            f"Ensemble members advected different particle counts {sorted(per_member_counts)} — "
            "run_backward_ensemble() is expected to apply the same "
            "min(config.n_particles, n_obs) decision to every member. "
            "Refusing to report a single n_particles value for a field that "
            "isn't actually uniform across members."
        )
    measured_n_particles = per_member_counts.pop()

    # ── Honest particle-loss accounting ──
    # "Lost" = simulated but not finite at the backward-time endpoint (the
    # position actually used as the origin estimate). A member that failed
    # outright is already excluded from ensemble_results by ensemble.py and
    # is reflected in ensemble_members_completed below, not here.
    particles_seeded = sum(hist_lons.shape[0] for hist_lons, _, _ in ensemble_results)
    final_lons = np.concatenate([hist_lons[:, -1] for hist_lons, _, _ in ensemble_results])
    final_lats = np.concatenate([hist_lats[:, -1] for _, hist_lats, _ in ensemble_results])
    finite_final = np.isfinite(final_lons) & np.isfinite(final_lats)
    particles_lost = int(particles_seeded - int(finite_final.sum()))

    # 1. Collect all particle endpoints from each ensemble member, dropping
    #    any trajectory whose particle went non-finite at any point — a
    #    single NaN would otherwise propagate through np.min/np.max below
    #    and corrupt the entire grid for every particle, not just the lost
    #    one. This is numerical hygiene around histogram construction, not a
    #    change to the advection mathematics in engine.py.
    all_lons = []
    all_lats = []
    all_times = []

    for hist_lons, hist_lats, hist_times in ensemble_results:
        n_particles, n_steps = hist_lons.shape
        finite_particle = np.all(np.isfinite(hist_lons), axis=1) & np.all(np.isfinite(hist_lats), axis=1)
        for step in range(n_steps):
            t = hist_times[step]
            all_lons.append(hist_lons[finite_particle, step])
            all_lats.append(hist_lats[finite_particle, step])
            all_times.append(np.full(int(finite_particle.sum()), t))

    all_lons = np.concatenate(all_lons)
    all_lats = np.concatenate(all_lats)
    all_times = np.concatenate(all_times)

    if all_lons.size == 0:
        raise ValueError(
            "Every particle went non-finite before the origin estimate could "
            "be built (particles_lost == particles_seeded). Cannot construct "
            "a Phi field from zero surviving trajectories."
        )

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

    # ── Convergence: ensemble-split divergence metric ──
    # Split the completed members into two halves, build an independent
    # (unweighted — no age-prior weighting, since this measures ensemble
    # agreement on WHERE the particles end up, not the age-conditioned
    # answer) lat/lon histogram from each half on the same edges as the
    # final grid, and measure how much the two halves disagree. This is a
    # real statistic computed over the already-completed ensemble members;
    # engine.py's advection math is untouched.
    n_completed = len(ensemble_results)
    if n_completed < 2:
        # Cannot split fewer than 2 members in half to measure agreement.
        # 1.0 (maximally divergent) is a conservative sentinel for any code
        # that reads the raw number without checking the flag first;
        # convergence_flag=INSUFFICIENT_PARTICLES is the authoritative
        # signal and is what the validity gate actually checks.
        convergence = 1.0
        convergence_flag = ConvergenceFlag.INSUFFICIENT_PARTICLES
    else:
        half = n_completed // 2

        def _lat_lon_hist(members):
            lons_h, lats_h = [], []
            for hlon, hlat, _ in members:
                finite = np.isfinite(hlon) & np.isfinite(hlat)
                lons_h.append(hlon[finite])
                lats_h.append(hlat[finite])
            lons_h = np.concatenate(lons_h) if lons_h else np.array([])
            lats_h = np.concatenate(lats_h) if lats_h else np.array([])
            if lons_h.size == 0:
                return np.zeros((n_y, n_x))
            h, _, _ = np.histogram2d(lats_h, lons_h, bins=[lat_edges, lon_edges])
            s = h.sum()
            return h / s if s > 0 else h

        hist_a = _lat_lon_hist(ensemble_results[:half])
        hist_b = _lat_lon_hist(ensemble_results[half:])
        # Total variation distance between the two half-ensemble estimates,
        # in [0, 1]: 0 = identical, 1 = disjoint support. Thresholded
        # against the existing PratiConfig.convergence_threshold (already
        # defined as "KL divergence threshold" for exactly this purpose,
        # unused until now).
        convergence = float(0.5 * np.abs(hist_a - hist_b).sum())
        if convergence <= config.convergence_threshold:
            convergence_flag = ConvergenceFlag.CONVERGED
        elif convergence <= 2 * config.convergence_threshold:
            convergence_flag = ConvergenceFlag.MARGINAL
        else:
            convergence_flag = ConvergenceFlag.NOT_CONVERGED

    # ── Spatial mode count and boundary interaction, from the built field ──
    # lat-lon marginal (sum over time) of the actual phi_array returned to
    # NYAYA — not a re-derivation from raw particles.
    spatial_marginal = phi_array.sum(axis=0)  # (n_y, n_x)
    peak = float(spatial_marginal.max())
    if peak > 0:
        mode_mask = spatial_marginal >= (_MODE_MASS_FRACTION * peak)
        _labeled, n_modes = ndimage.label(mode_mask)
    else:
        n_modes = 0
    n_modes = int(n_modes)
    multimodal = n_modes > 1

    # Mass in the outermost ring of the auto-fit grid. The grid is fit to the
    # data with only a one-cell margin (see lon_min/lat_min above), so this
    # measures whether trajectories reached the edge of the rendered domain
    # — there is no coastline model in this tranche, so this is a grid-
    # boundary signal, not a coastal one.
    edge_mass = float(
        spatial_marginal[0, :].sum() + spatial_marginal[-1, :].sum()
        + spatial_marginal[:, 0].sum() + spatial_marginal[:, -1].sum()
    )
    boundary_interaction = edge_mass > 0.01

    diagnostics = PhiDiagnostics(
        entropy=entropy,
        concentration=concentration,
        effective_support_km2=effective_support_km2,
        convergence=convergence,
        convergence_flag=convergence_flag,
        n_modes=n_modes,
        multimodal=multimodal,
        boundary_interaction=boundary_interaction,
        particles_lost=particles_lost,
        particles_seeded=particles_seeded,
        ensemble_members_completed=n_completed,
        ensemble_members_requested=config.n_ensemble,
        runtime_seconds=runtime_seconds,
    )

    # This single (cheap, 1-ensemble-run) build path never computes
    # sensitivity — that requires re-running the ensemble at perturbed
    # age/forcing/diffusivity settings, which costs 7x this function's
    # runtime. See varuna_prativartan.sensitivity.run_sensitivity_sweep()
    # + build_sensitivity_block() (ADR-0007, ratified) for the real,
    # non-fabricated computation, invoked separately by callers that
    # explicitly want it. Leaving sensitivity=None here (rather than
    # silently running the expensive sweep on every case) is deliberate;
    # the validity gate treats None as GateReason.PHI_DIAGNOSTICS_UNAVAILABLE
    # and fails closed rather than trusting a manufactured number.
    sensitivity = None

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
        n_particles=measured_n_particles,
        n_ensemble=config.n_ensemble,
        backward_duration_hours=config.backward_duration_hours,
        dt_seconds=config.dt_seconds,
        forcing_current_source="synthetic_shear_v1",
        forcing_wind_source="synthetic_wind_v1",
        weathering_model=None,
        envelope=out_env,
        created_at=datetime.now(timezone.utc),
    )
