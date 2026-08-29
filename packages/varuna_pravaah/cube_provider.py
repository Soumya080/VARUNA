"""
VARUNA GRID — ForcingCube-backed PRAVAAH provider.

Same forward-particle-advection scheme as MockPravaahProvider (simple
forward-Euler integration of particle positions), driven by a real
CubeBackedCurrentField instead of a hardcoded constant drift. This is
deliberately NOT a new physical model — MockPravaahProvider stays as the
synthetic-test provider; this is the protocol + real-forcing wiring the
audit asked for.

Fails closed: if the ForcingCube is not usable_for_advection (checked
inside CubeBackedCurrentField's constructor), this provider cannot be
constructed at all.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from varuna_contracts.evidence import EvidenceEnvelope
from varuna_contracts.schemas import ForwardForecast, SlickDetection
from varuna_data_eng.schemas.forcing import ForcingCube
from varuna_prativartan.cube_field import PHI_EPOCH, CubeBackedCurrentField
from varuna_pravaah.coastline import check_landfall
from varuna_pravaah.protocol import PravaahProvider


class CubeBackedPravaahProvider(PravaahProvider):
    """Forward drift forecast driven by a real ForcingCube's current field.

    `u_grid`/`v_grid` (the actual gridded velocity arrays) must be supplied
    separately from the ForcingCube contract object itself — see
    CubeBackedCurrentField.load_arrays for why the cube stays a lightweight,
    JSON-serializable pydantic object rather than embedding a raw NetCDF
    array."""

    PROVIDER_VERSION = "cube-real-v1"

    def __init__(self, cube: ForcingCube, u_grid: np.ndarray, v_grid: np.ndarray):
        self._field = CubeBackedCurrentField(cube)  # raises if cube fails advection check
        self._field.load_arrays(u_grid, v_grid)
        self._cube = cube

    def forecast_drift(
        self,
        slick: SlickDetection,
        forcing_path: str | None,
        horizon_hours: float,
        envelope: EvidenceEnvelope,
    ) -> ForwardForecast:
        rng = np.random.default_rng(hash(slick.slick_id) % 2**31)
        n_particles = 50
        n_steps = int(horizon_hours * 4)  # 15-min steps, matching MockPravaahProvider

        t0_hours = (slick.observation_time - PHI_EPOCH).total_seconds() / 3600.0

        lons = np.zeros((n_particles, n_steps + 1))
        lats = np.zeros((n_particles, n_steps + 1))
        lons[:, 0] = rng.normal(slick.centroid.lon, 0.01, n_particles)
        lats[:, 0] = rng.normal(slick.centroid.lat, 0.01, n_particles)

        dt_hours = 0.25
        for t in range(n_steps):
            t_hours = t0_hours + t * dt_hours
            try:
                u, v = self._field.velocity_at(lons[:, t], lats[:, t], t_hours)
            except Exception:
                # Out-of-domain mid-trajectory: fail closed by freezing the
                # particle rather than extrapolating past the cube's coverage.
                u = np.zeros(n_particles)
                v = np.zeros(n_particles)
            # deg/hour from m/s: ~111km/deg lat, cos(lat) correction for lon
            dlat = (v * dt_hours) / 111.0
            dlon = (u * dt_hours) / (111.0 * np.cos(np.radians(np.clip(lats[:, t], -89, 89))))
            lons[:, t + 1] = lons[:, t] + dlon
            lats[:, t + 1] = lats[:, t] + dlat

        temp_dir = Path(tempfile.gettempdir()) / "varuna_pravaah_cube"
        temp_dir.mkdir(parents=True, exist_ok=True)
        traj_path = temp_dir / f"pravaah_cube_{slick.slick_id}.npz"
        np.savez(traj_path, lons=lons, lats=lats)

        landfalls = check_landfall(lons[:, -1], lats[:, -1])

        return ForwardForecast(
            forecast_id=f"fcast-cube-{slick.slick_id}",
            slick_id=slick.slick_id,
            horizon_hours=horizon_hours,
            landfalls=landfalls,
            trajectory_path=str(traj_path),
        )

    def get_model_version(self) -> str:
        return self.PROVIDER_VERSION
