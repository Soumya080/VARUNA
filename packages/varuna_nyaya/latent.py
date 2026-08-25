"""
VARUNA GRID — Latent-source hypothesis L0 computation.

This module is maintained for backward compatibility.
New code should use likelihoods.compute_density_likelihoods.
"""
import numpy as np
from typing import List, Dict, Tuple
from varuna_contracts.schemas import VesselTrack
from varuna_nyaya.corridor import build_corridor_mask, build_union_mask, integrate_phi_over_mask


def compute_likelihoods_and_latent(
    phi_data: np.ndarray,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,
    tracks: List[VesselTrack],
    corridor_width_km: float = 5.0,
) -> Tuple[Dict[str, float], float]:
    """
    Computes raw per-vessel likelihoods (L_k) and latent probability (L0).

    DEPRECATED: Use likelihoods.compute_density_likelihoods for
    scientifically sound inference. Raw mass likelihoods have a
    structural domain mismatch that causes latent to trivially dominate.
    """
    likelihoods = {}
    masks = []

    for track in tracks:
        mask = build_corridor_mask(
            track=track, phi_data=phi_data,
            lon_edges=lon_edges, lat_edges=lat_edges,
            time_edges=time_edges, corridor_width_km=corridor_width_km,
        )
        L_k = integrate_phi_over_mask(phi_data, mask)
        likelihoods[track.mmsi] = L_k
        masks.append(mask)

    if masks:
        union_mask = build_union_mask(masks)
        covered_mass = integrate_phi_over_mask(phi_data, union_mask)
        L_0 = 1.0 - covered_mass
    else:
        L_0 = 1.0

    L_0 = max(0.0, min(1.0, L_0))
    return likelihoods, L_0
