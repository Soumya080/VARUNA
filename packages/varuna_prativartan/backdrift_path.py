"""
VARUNA GRID — derived backward-drift path (ADR-0017).

`build_phi_field()` collapses every particle's real backward trajectory into
a 3D probability histogram (`phi_array`, shape (n_t, n_y, n_x)) and discards
the individual paths. This module derives one honest, real summary of that
histogram: the probability-mass-weighted centroid (lon, lat) of each time
slice, in backward-time order from the observation moment to the oldest
time bin.

This is NOT a reconstruction of any single particle's path — Phi is a
distribution over an ensemble of many particles, and the centroid is only a
faithful one-line summary of "where the probability mass is" at each time
step. It is most misleading exactly when the field is multimodal (see
`PhiDiagnostics.multimodal`); callers must carry that flag alongside the
path, never present it as "the" answer without checking it.
"""
from __future__ import annotations

import numpy as np

from varuna_contracts.phi import BackdriftPathPoint


def derive_centroid_path(
    phi_array: np.ndarray,
    lon_edges: np.ndarray,
    lat_edges: np.ndarray,
    time_edges: np.ndarray,
    obs_time_hours: float,
) -> list[BackdriftPathPoint]:
    """`phi_array`: (n_t, n_y, n_x) float array, need not already sum to 1
    (a slice with zero mass is simply omitted from the path — there is no
    honest centroid for a time bin the ensemble never populated).
    `lon_edges`/`lat_edges`/`time_edges`: the bin boundaries `build_phi_field`
    already computes. `obs_time_hours`: the observation instant, so each
    point's `time_hours` can be reported as backward AGE (>= 0) rather than
    an opaque absolute coordinate — the same honesty fix M3 made for
    `ObservationView.observation_time` applies here: an operator-facing time
    field should be a real, interpretable quantity, not an internal one.
    """
    lon_centers = 0.5 * (lon_edges[:-1] + lon_edges[1:])
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    time_centers = 0.5 * (time_edges[:-1] + time_edges[1:])

    n_t = phi_array.shape[0]
    total_mass = float(phi_array.sum())
    if total_mass <= 0:
        return []

    points: list[BackdriftPathPoint] = []
    for t_idx in range(n_t):
        sl = phi_array[t_idx]  # (n_y, n_x)
        slice_mass = float(sl.sum())
        if slice_mass <= 0:
            continue
        # Probability-weighted centroid within this time slice.
        y_idx, x_idx = np.indices(sl.shape)
        lon = float((sl * lon_centers[np.newaxis, :]).sum() / slice_mass)
        lat = float((sl * lat_centers[:, np.newaxis]).sum() / slice_mass)
        # time_centers[t_idx] is Phi's internal epoch-relative coordinate
        # (same PHI_EPOCH family as the M3 fix); age is always >= 0 by
        # construction since these are backward-integration time bins.
        age_hours = max(0.0, obs_time_hours - time_centers[t_idx])
        points.append(BackdriftPathPoint(
            time_hours=age_hours, lon=lon, lat=lat,
            mass_fraction=slice_mass / total_mass,
        ))

    # Backward order: oldest (largest age) first, observation last — the
    # natural reading order for an animated "tracing the slick back to its
    # origin" visual.
    points.sort(key=lambda p: -p.time_hours)
    return points
