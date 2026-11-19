"""
VARUNA GRID — ForcingCube-backed current/wind fields for PRATIVARTAN.

These implement the same AbstractCurrentField / AbstractWindField ABCs as
the Synthetic* fields in current_field.py — PRATIVARTAN's advection
mathematics are untouched. This module is purely the missing seam: a real
ForcingCube in, the same velocity_at(lons, lats, t_hours) -> (u, v) out.

Fail-closed by construction:
  - A cube with time_series_status != SUFFICIENT is rejected at __init__,
    not silently used to extrapolate from a single timestep.
  - A query outside the cube's spatial or temporal domain raises rather
    than extrapolating.
"""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from varuna_data_eng.schemas.forcing import ForcingCube
from varuna_prativartan.current_field import AbstractCurrentField, AbstractWindField

# Shared with varuna_nyaya/scorer.py and corridor.py and
# varuna_prativartan/phi_builder.py, which independently hardcode the same
# constant today (docs/adr territory to fully unify — flagged, not fixed
# here since it touches four files' semantics at once).
PHI_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class OutOfDomainError(ValueError):
    """Raised when a query falls outside a ForcingCube's spatial or temporal
    coverage. PRATIVARTAN must fail closed here, never extrapolate."""


class _CubeField:
    """Shared interpolation logic for current/wind cube-backed fields.
    Not itself an ABC implementation — subclassed by the two below."""

    def __init__(self, cube: ForcingCube, u_var: str, v_var: str):
        # Fails closed immediately if the cube cannot support advection.
        cube.assert_usable_for_advection()

        self._cube = cube
        self._u_var = u_var
        self._v_var = v_var

        self._lat = np.asarray(cube.lat_coords, dtype=float)
        self._lon = np.asarray(cube.lon_coords, dtype=float)
        self._time_hours = np.array(
            [(t - PHI_EPOCH).total_seconds() / 3600.0 for t in cube.time_coords]
        )

        var_names = {v.name for v in cube.variables}
        if u_var not in var_names or v_var not in var_names:
            raise ValueError(
                f"ForcingCube {cube.cube_id!r} does not declare variables "
                f"{u_var!r}/{v_var!r}; has {sorted(var_names)}."
            )

        # The cube schema carries coordinates and metadata but not the raw
        # gridded array — actual velocity values are loaded lazily from
        # cube.data_path by the caller-provided loader in `from_cube_and_arrays`,
        # or must be attached via `.load_arrays()` before `velocity_at` is
        # callable. This keeps ForcingCube (a pydantic contract object)
        # lightweight and JSON-serializable rather than embedding a NetCDF
        # array inside it.
        self._u_grid: np.ndarray | None = None
        self._v_grid: np.ndarray | None = None

    def load_arrays(self, u_grid: np.ndarray, v_grid: np.ndarray) -> None:
        """Attach the actual (time, lat, lon) velocity arrays. Shape must be
        (n_time, n_lat, n_lon) or (n_lat, n_lon) for a single-timestep cube
        that has already passed assert_usable_for_advection (i.e. never, in
        practice — single-timestep cubes are rejected at __init__. This
        shape is accepted for symmetry/testing only)."""
        expected_2d = (len(self._lat), len(self._lon))
        expected_3d = (len(self._time_hours), len(self._lat), len(self._lon))
        for name, grid in (("u", u_grid), ("v", v_grid)):
            if grid.shape not in (expected_2d, expected_3d):
                raise ValueError(
                    f"{name}_grid shape {grid.shape} does not match cube "
                    f"dimensions (expected {expected_2d} or {expected_3d})."
                )
        self._u_grid = u_grid
        self._v_grid = v_grid

    def _check_domain(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> None:
        if self._u_grid is None or self._v_grid is None:
            raise RuntimeError(
                f"{type(self).__name__} for cube {self._cube.cube_id!r} has "
                f"no velocity arrays loaded — call load_arrays() first."
            )
        lon_lo, lon_hi = float(self._lon.min()), float(self._lon.max())
        lat_lo, lat_hi = float(self._lat.min()), float(self._lat.max())
        if np.any(lons < lon_lo) or np.any(lons > lon_hi) or \
           np.any(lats < lat_lo) or np.any(lats > lat_hi):
            raise OutOfDomainError(
                f"Query point(s) outside ForcingCube {self._cube.cube_id!r} "
                f"spatial domain lon=[{lon_lo},{lon_hi}] lat=[{lat_lo},{lat_hi}]. "
                f"Refusing to extrapolate."
            )
        t_lo, t_hi = float(self._time_hours.min()), float(self._time_hours.max())
        if t_hours < t_lo or t_hours > t_hi:
            raise OutOfDomainError(
                f"Query time t_hours={t_hours} outside ForcingCube "
                f"{self._cube.cube_id!r} temporal domain [{t_lo},{t_hi}]. "
                f"Refusing to extrapolate."
            )

    def _interpolate(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> tuple[np.ndarray, np.ndarray]:
        self._check_domain(lons, lats, t_hours)

        if self._u_grid.ndim == 2:
            u_slice, v_slice = self._u_grid, self._v_grid
        else:
            t_idx = int(np.searchsorted(self._time_hours, t_hours))
            t_idx = min(max(t_idx, 0), len(self._time_hours) - 1)
            u_slice, v_slice = self._u_grid[t_idx], self._v_grid[t_idx]

        lat_asc = self._lat if self._lat[0] < self._lat[-1] else self._lat[::-1]
        lon_asc = self._lon

        def bilinear(grid: np.ndarray) -> np.ndarray:
            g = grid if self._lat[0] < self._lat[-1] else grid[::-1, :]
            out = np.empty(len(lons), dtype=float)
            for i, (lo, la) in enumerate(zip(lons, lats)):
                ix = np.clip(np.searchsorted(lon_asc, lo) - 1, 0, len(lon_asc) - 2)
                iy = np.clip(np.searchsorted(lat_asc, la) - 1, 0, len(lat_asc) - 2)
                x0, x1 = lon_asc[ix], lon_asc[ix + 1]
                y0, y1 = lat_asc[iy], lat_asc[iy + 1]
                fx = 0.0 if x1 == x0 else (lo - x0) / (x1 - x0)
                fy = 0.0 if y1 == y0 else (la - y0) / (y1 - y0)
                v00, v10 = g[iy, ix], g[iy, ix + 1]
                v01, v11 = g[iy + 1, ix], g[iy + 1, ix + 1]
                out[i] = (
                    v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy)
                    + v01 * (1 - fx) * fy + v11 * fx * fy
                )
            return out

        return bilinear(u_slice), bilinear(v_slice)


class CubeBackedCurrentField(_CubeField, AbstractCurrentField):
    """AbstractCurrentField backed by a real ForcingCube (CMEMS uo/vo)."""

    def __init__(self, cube: ForcingCube):
        super().__init__(cube, u_var="uo", v_var="vo")

    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> tuple[np.ndarray, np.ndarray]:
        return self._interpolate(np.asarray(lons, dtype=float), np.asarray(lats, dtype=float), t_hours)


class CubeBackedWindField(_CubeField, AbstractWindField):
    """AbstractWindField backed by a real ForcingCube (ERA5 u10/v10)."""

    def __init__(self, cube: ForcingCube):
        super().__init__(cube, u_var="u10", v_var="v10")

    def velocity_at(self, lons: np.ndarray, lats: np.ndarray, t_hours: float) -> tuple[np.ndarray, np.ndarray]:
        return self._interpolate(np.asarray(lons, dtype=float), np.asarray(lats, dtype=float), t_hours)
