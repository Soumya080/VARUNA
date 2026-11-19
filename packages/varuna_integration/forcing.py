"""
Phase 4 - real forcing boundary.

    MC20 ERA5 + MC20 CMEMS  ->  ForcingCube  ->  CubeBackedWindField
                                             ->  CubeBackedCurrentField
                                             ->  PRATIVARTAN / PRAVAAH

This is wiring, not a second forcing architecture. `ForcingCube`,
`CubeBackedWindField`/`CubeBackedCurrentField` and
`load_era5_wind_arrays()`/`load_cmems_current_arrays()` all already exist and
are reused unmodified. What was missing was a single place that loads both
cubes for an event, fails closed on every way that can go wrong, and reports
the usable time overlap between them.

Fails closed on: missing cube file, missing variables, missing/insufficient
time series, spatial coverage that does not contain the query, out-of-domain
query time, and a non-overlapping ERA5/CMEMS window. Each produces a named
BLOCKED reason - never a silently substituted constant drift.

One environment hazard to be aware of. On this machine, `xr.open_dataset(path)`
with NO explicit engine (letting xarray auto-detect) has been observed to hang
indefinitely on the real MC20 `.nc` files, by two sessions independently. The
canonical readers used here pass `engine="netcdf4"` explicitly and do NOT hang -
measured at 0.75s (ERA5) and 0.18s (CMEMS). A first cold read of these files can
still take ~20s on the spinning disk while it is also serving training, which is
slowness, not a hang; do not mistake one for the other.

Schema imports are kept at module top regardless, because importing `netCDF4`
before the pydantic schema modules deadlocks those imports on Windows here (a
DLL-search-path interaction found by the dataset track).
"""
from __future__ import annotations

# Schema imports MUST precede anything that may import netCDF4. See docstring.
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance  # isort: skip
from varuna_data_eng.schemas.forcing import ForcingCube  # isort: skip

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from varuna_integration.stage import StageResult, StageStatus


@dataclass
class EventForcing:
    """Both real forcing fields for one event, plus their usable time window."""

    wind_field: object          # CubeBackedWindField
    current_field: object       # CubeBackedCurrentField
    era5_cube: ForcingCube
    cmems_cube: ForcingCube
    overlap_lo_hours: float
    overlap_hi_hours: float
    envelope: EvidenceEnvelope

    def clamp_time(self, t_hours: float, margin_hours: float = 1.0) -> tuple[float, bool]:
        """Clamp a query time into the ERA5/CMEMS overlap.

        Returns `(t, was_clamped)`. The caller must record `was_clamped` - a
        silently moved observation time is a fabricated observation time.
        """
        lo = self.overlap_lo_hours + margin_hours
        hi = self.overlap_hi_hours - margin_hours
        t = min(max(t_hours, lo), hi)
        return t, t != t_hours

    def covers(self, t_hours: float) -> bool:
        return self.overlap_lo_hours <= t_hours <= self.overlap_hi_hours


def load_event_forcing(gold_dir: Path, *, source_id: str = "era5.real+cmems.real"
                       ) -> StageResult:
    """Load both real cubes for an event Gold directory.

    Every failure mode returns BLOCKED with a named reason rather than raising,
    so a case can record "forcing unavailable" and continue to an honest
    terminal state instead of crashing.
    """
    from varuna_prativartan.cube_field import (
        PHI_EPOCH, CubeBackedCurrentField, CubeBackedWindField,
    )
    from varuna_source_adapters.forcing_readers import (
        load_cmems_current_arrays, load_era5_wind_arrays,
    )

    t0 = time.perf_counter()

    def blocked(reason: str) -> StageResult:
        return StageResult(
            stage="forcing", status=StageStatus.BLOCKED,
            evidence_mode=EvidenceMode.UNAVAILABLE, reason=reason,
            runtime_seconds=time.perf_counter() - t0,
        )

    era5_path = gold_dir / "forcing" / "era5_cube.json"
    cmems_path = gold_dir / "forcing" / "cmems_cube.json"
    for p, name in ((era5_path, "ERA5"), (cmems_path, "CMEMS")):
        if not p.exists():
            return blocked(f"{name}_CUBE_MISSING: {p} does not exist.")

    try:
        era5_cube = ForcingCube(**json.loads(era5_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return blocked(f"ERA5_CUBE_INVALID: {type(exc).__name__}: {exc}")
    try:
        cmems_cube = ForcingCube(**json.loads(cmems_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return blocked(f"CMEMS_CUBE_INVALID: {type(exc).__name__}: {exc}")

    # CubeBackedWindField/CurrentField call assert_usable_for_advection() in
    # their constructors - insufficient time series or partial spatial coverage
    # raises here rather than producing a field that quietly extrapolates.
    try:
        wind_field = CubeBackedWindField(era5_cube)
        u_w, v_w = load_era5_wind_arrays(era5_cube)
        wind_field.load_arrays(u_w, v_w)
    except Exception as exc:
        return blocked(
            f"ERA5_FIELD_UNUSABLE: {type(exc).__name__}: {exc} "
            f"(cube={era5_cube.cube_id}, time_series_status="
            f"{getattr(era5_cube.time_series_status, 'value', '?')})"
        )
    try:
        current_field = CubeBackedCurrentField(cmems_cube)
        u_c, v_c = load_cmems_current_arrays(cmems_cube)
        current_field.load_arrays(u_c, v_c)
    except Exception as exc:
        return blocked(
            f"CMEMS_FIELD_UNUSABLE: {type(exc).__name__}: {exc} "
            f"(cube={cmems_cube.cube_id}, time_series_status="
            f"{getattr(cmems_cube.time_series_status, 'value', '?')})"
        )

    def hours(t: datetime) -> float:
        return (t - PHI_EPOCH).total_seconds() / 3600.0

    lo = max(hours(era5_cube.time_coords[0]), hours(cmems_cube.time_coords[0]))
    hi = min(hours(era5_cube.time_coords[-1]), hours(cmems_cube.time_coords[-1]))
    if hi <= lo:
        return blocked(
            "FORCING_WINDOWS_DISJOINT: ERA5 covers "
            f"[{era5_cube.time_coords[0]}, {era5_cube.time_coords[-1]}] and CMEMS "
            f"[{cmems_cube.time_coords[0]}, {cmems_cube.time_coords[-1]}] - no "
            "overlapping time window, so no advection is possible."
        )

    envelope = EvidenceEnvelope(
        artifact_id=f"forcing-{gold_dir.name}",
        produced_by="varuna_integration.forcing",
        provenance=Provenance(
            source_id=source_id,
            notes=(
                f"ERA5 cube={era5_cube.cube_id} ({u_w.shape}); "
                f"CMEMS cube={cmems_cube.cube_id} ({u_c.shape}); "
                f"overlap {hi - lo:.1f}h"
            ),
        ),
        mode=EvidenceMode.REAL,
    )
    forcing = EventForcing(
        wind_field=wind_field, current_field=current_field,
        era5_cube=era5_cube, cmems_cube=cmems_cube,
        overlap_lo_hours=lo, overlap_hi_hours=hi, envelope=envelope,
    )
    return StageResult(
        stage="forcing", status=StageStatus.PRODUCED, value=forcing,
        evidence_mode=EvidenceMode.REAL,
        runtime_seconds=time.perf_counter() - t0,
        detail={
            "era5_cube_id": era5_cube.cube_id,
            "cmems_cube_id": cmems_cube.cube_id,
            "era5_time_series_status": era5_cube.time_series_status.value,
            "cmems_time_series_status": cmems_cube.time_series_status.value,
            "era5_grid_shape": list(u_w.shape),
            "cmems_grid_shape": list(u_c.shape),
            "overlap_hours": hi - lo,
        },
    )


def probe_forcing(forcing: EventForcing, lon: float, lat: float, t_hours: float
                  ) -> dict[str, tuple[float, float] | str]:
    """Sample both fields at one point. Out-of-domain is reported, not clamped."""
    out: dict[str, tuple[float, float] | str] = {}
    for name, field in (("wind", forcing.wind_field), ("current", forcing.current_field)):
        try:
            u, v = field.velocity_at(np.array([lon]), np.array([lat]), t_hours)
            out[name] = (float(u[0]), float(v[0]))
        except Exception as exc:
            out[name] = f"OUT_OF_DOMAIN: {type(exc).__name__}: {exc}"
    return out
