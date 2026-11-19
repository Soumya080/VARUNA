"""
VARUNA GRID — Density-Based Likelihood Computation.

Instead of comparing raw Phi mass (which structurally favours the latent
hypothesis because the ocean volume >> corridor volume), we compare Phi
DENSITY (mass per unit voxel volume).

    rho_k = L_k / V_k   (Phi density inside vessel k's corridor)
    rho_0 = L_0 / V_0   (Phi density outside all corridors)

This eliminates the structural domain mismatch WITHOUT any tunable parameter.
"""
import numpy as np
from typing import List, Dict, Tuple, Any
from varuna_contracts.schemas import VesselTrack
from varuna_nyaya.corridor import (
    build_corridor_mask, build_union_mask, integrate_phi_over_mask,
)


def compute_density_likelihoods(
    phi_data: np.ndarray,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,
    tracks: List[VesselTrack],
    corridor_width_km: float = 5.0,
) -> Tuple[Dict[str, float], float, Dict[str, Any]]:
    """
    Compute density-based likelihoods for all vessel hypotheses and latent.

    Returns:
        densities: {mmsi: rho_k} per-vessel Phi density
        rho_0: background Phi density (latent hypothesis)
        diagnostics: raw masses, volumes, partition info for audit
    """
    masks = {}
    raw_masses = {}
    volumes = {}

    for track in tracks:
        mask = build_corridor_mask(
            track=track,
            phi_data=phi_data,
            lon_edges=lon_edges,
            lat_edges=lat_edges,
            time_edges=time_edges,
            corridor_width_km=corridor_width_km,
        )
        masks[track.mmsi] = mask
        L_k = integrate_phi_over_mask(phi_data, mask)
        V_k = int(mask.sum())
        raw_masses[track.mmsi] = L_k
        volumes[track.mmsi] = V_k

    # Union mask and residual
    mask_list = list(masks.values())
    if mask_list:
        union_mask = build_union_mask(mask_list)
        covered_mass = integrate_phi_over_mask(phi_data, union_mask)
        V_union = int(union_mask.sum())
    else:
        union_mask = None
        covered_mass = 0.0
        V_union = 0

    total_voxels = phi_data.size
    L_0 = max(0.0, min(1.0, 1.0 - covered_mass))
    V_0 = max(1, total_voxels - V_union)

    # Compute densities
    densities = {}
    for mmsi in raw_masses:
        V_k = max(1, volumes[mmsi])
        densities[mmsi] = raw_masses[mmsi] / V_k

    rho_0 = L_0 / V_0

    diagnostics = {
        "raw_masses": raw_masses,
        "volumes": volumes,
        "L_0": L_0,
        "V_0": V_0,
        "V_union": V_union,
        "total_voxels": total_voxels,
        "covered_mass": covered_mass,
        "partition_sum": sum(raw_masses.values()) + L_0,
    }

    return densities, rho_0, diagnostics


def compute_raw_likelihoods(
    phi_data: np.ndarray,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,
    tracks: List[VesselTrack],
    corridor_width_km: float = 5.0,
) -> Tuple[Dict[str, float], float]:
    """
    Legacy raw-mass likelihoods (for backward compatibility).
    Prefer compute_density_likelihoods for scientifically sound inference.
    """
    densities, rho_0, diag = compute_density_likelihoods(
        phi_data, lon_edges, lat_edges, time_edges, tracks, corridor_width_km
    )
    return diag["raw_masses"], diag["L_0"]
