"""
VARUNA GRID — MC20 forcing readers, netCDF4 backend.

Builds the exact same `ForcingCube` contract as
`varuna_source_adapters.forcing_readers` (reused, not duplicated) --
these functions exist only because `xarray.open_dataset()` was observed
to hang indefinitely and unpredictably on the two real MC20 forcing
files (`era5_mc20_2023-01-11_to_2023-01-17.nc`,
`cmems_mc20_2023-01-11_to_2023-01-17.nc`) in this environment,
reproduced across multiple separate runs (see
docs/datasets/MC20_REAL_E2E_ACQUISITION_FINAL.md sections 5 and 23).
`netCDF4` opens both files instantly.

Also: `read_era5_grib()` in forcing_readers.py requires GRIB1 +
cfgrib -- the MC20 ERA5 file was acquired in NetCDF format (CDS API
`"format": "netcdf"`), so that function does not apply here regardless
of the xarray issue. This module's `read_era5_netcdf4()` fills that
real gap for a NetCDF-format ERA5 file.

This is additive, MC20-specific code. It does not modify
forcing_readers.py (Track-2-owned) and does not change the ForcingCube
schema in any way -- every field populated here matches the meaning
and type of the equivalent field in read_era5_grib()/read_cmems_netcdf().

Read-only. Never modifies the source NetCDF file.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

# IMPORT ORDER MATTERS ON WINDOWS: importing netCDF4 (which bundles its own
# HDF5/curl native DLLs) *before* the pydantic-based varuna_contracts/
# varuna_data_eng schema modules causes those schema imports to hang
# indefinitely and reproducibly in this environment (a DLL-search-path
# interaction, not a logic bug -- confirmed by isolating the two import
# orders directly). Schemas are imported first here for that reason;
# never reorder this without re-testing both directions.
from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.forcing import (
    ForcingCube,
    ForcingSource,
    ForcingVariable,
    SpatialCoverageStatus,
    TimeSeriesStatus,
)
from varuna_data_eng.schemas.provenance import DataProvenance

import netCDF4 as nc4
import numpy as np


def _file_checksum(path: Path, limit_bytes: int = 8 * 1024 * 1024) -> tuple[str, bool]:
    """Same policy as forcing_readers._file_checksum: real sha256 under the
    size limit, a size+mtime fallback digest above it (mirrored here rather
    than imported to keep this module import-independent of xarray, which
    forcing_readers.py imports at module level)."""
    size = path.stat().st_size
    if size > limit_bytes:
        fallback = f"size:{size}:mtime:{int(path.stat().st_mtime)}"
        return hashlib.sha256(fallback.encode()).hexdigest(), False
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest(), True


def read_era5_netcdf4(path: Path, *, adapter_id: str = "era5.real.mc20") -> ForcingCube:
    """Build a ForcingCube from the real MC20 ERA5 NetCDF file (u10/v10),
    via netCDF4 directly. See module docstring for why xarray is avoided."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ERA5 NetCDF file not found: {path}")

    with nc4.Dataset(path) as ds:
        var_map = {"u10": "10m_u_component_of_wind", "v10": "10m_v_component_of_wind"}
        missing = [v for v in var_map if v not in ds.variables]
        if missing:
            raise ValueError(
                f"ERA5 file {path} is missing required variable(s) {missing}; "
                f"found {list(ds.variables)}. Refusing to build a partial cube."
            )

        lat = np.asarray(ds.variables["latitude"][:], dtype=float)
        lon = np.asarray(ds.variables["longitude"][:], dtype=float)
        if lat.ndim != 1 or lon.ndim != 1:
            raise ValueError(f"ERA5 file {path} has a non-1D coordinate grid; unsupported.")

        tname = "valid_time" if "valid_time" in ds.variables else "time"
        tvar = ds.variables[tname]
        time_vals = nc4.num2date(tvar[:], tvar.units)
        time_coords = [
            datetime(t.year, t.month, t.day, t.hour, t.minute, t.second, tzinfo=UTC)
            for t in np.atleast_1d(time_vals)
        ]
        time_series_status = (
            TimeSeriesStatus.SUFFICIENT if len(time_coords) >= 2 else TimeSeriesStatus.INSUFFICIENT
        )

        lat_min, lat_max = float(lat.min()), float(lat.max())
        lon_min, lon_max = float(lon.min()), float(lon.max())
        bbox = BBox(min_lon=lon_min, min_lat=lat_min, max_lon=lon_max, max_lat=lat_max)

        lat_res = float(abs(np.median(np.diff(lat)))) if len(lat) > 1 else 0.0
        lon_res = float(abs(np.median(np.diff(lon)))) if len(lon) > 1 else 0.0
        grid_res = round((lat_res + lon_res) / 2, 6) if (lat_res or lon_res) else 0.0

        if len(time_coords) >= 2:
            deltas_hours = np.diff(np.array([t.timestamp() for t in time_coords])) / 3600.0
            temporal_res = float(np.median(deltas_hours))
        else:
            temporal_res = 0.0

        u10 = ds.variables["u10"]
        v10 = ds.variables["v10"]
        u10_units = getattr(u10, "units", "m s**-1")
        v10_units = getattr(v10, "units", "m s**-1")

        checksum, is_real_hash = _file_checksum(path)
        size_bytes = path.stat().st_size

        return ForcingCube(
            cube_id=f"era5-mc20-{path.stem}",
            source=ForcingSource.ERA5,
            product_id="reanalysis-era5-single-levels:10m_wind",
            variables=[
                ForcingVariable(name="u10", unit=u10_units, standard_name=var_map["u10"]),
                ForcingVariable(name="v10", unit=v10_units, standard_name=var_map["v10"]),
            ],
            time_coords=time_coords,
            lat_coords=lat.tolist(),
            lon_coords=lon.tolist(),
            grid_resolution_deg=grid_res,
            temporal_resolution_hours=temporal_res,
            data_path=str(path),
            crs="EPSG:4326",
            bbox=bbox,
            time_range=(time_coords[0], time_coords[-1]),
            dataset_version=None,
            file_checksum=checksum,
            file_size_bytes=size_bytes,
            provenance=DataProvenance(
                source_id="era5.real.mc20",
                adapter_id=adapter_id,
                license="Copernicus Climate Change Service (C3S) License",
                raw_artifact_path=str(path),
                notes=(
                    ("sha256 computed" if is_real_hash else "checksum is a size+mtime fallback digest")
                    + "; read via netCDF4 (xarray hangs indefinitely on this exact file in this environment)"
                ),
            ),
            time_series_status=time_series_status,
            spatial_coverage_status=SpatialCoverageStatus.FULL,
        )


def read_cmems_netcdf4(path: Path, *, adapter_id: str = "cmems.real.mc20") -> ForcingCube:
    """Build a ForcingCube from the real MC20 CMEMS NetCDF file (uo/vo),
    via netCDF4 directly. See module docstring for why xarray is avoided."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CMEMS NetCDF file not found: {path}")

    with nc4.Dataset(path) as ds:
        var_map = {"uo": "eastward_sea_water_velocity", "vo": "northward_sea_water_velocity"}
        missing = [v for v in var_map if v not in ds.variables]
        if missing:
            raise ValueError(
                f"CMEMS file {path} is missing required variable(s) {missing}; "
                f"found {list(ds.variables)}. Refusing to build a partial cube."
            )

        lat_name = "latitude" if "latitude" in ds.variables else "lat"
        lon_name = "longitude" if "longitude" in ds.variables else "lon"
        lat = np.asarray(ds.variables[lat_name][:], dtype=float)
        lon = np.asarray(ds.variables[lon_name][:], dtype=float)

        n_time = ds.dimensions["time"].size if "time" in ds.dimensions else 1
        if "time" in ds.variables:
            tvar = ds.variables["time"]
            time_vals = nc4.num2date(tvar[:], tvar.units)
            time_coords = [
                datetime(t.year, t.month, t.day, t.hour, t.minute, t.second, tzinfo=UTC)
                for t in np.atleast_1d(time_vals)
            ]
        else:
            time_coords = [datetime.now(UTC)]

        time_series_status = (
            TimeSeriesStatus.SUFFICIENT if n_time >= 2 else TimeSeriesStatus.INSUFFICIENT
        )

        lat_min, lat_max = float(np.min(lat)), float(np.max(lat))
        lon_min, lon_max = float(np.min(lon)), float(np.max(lon))
        bbox = BBox(min_lon=lon_min, min_lat=lat_min, max_lon=lon_max, max_lat=lat_max)

        lat_res = float(abs(np.median(np.diff(lat)))) if len(lat) > 1 else 0.0
        lon_res = float(abs(np.median(np.diff(lon)))) if len(lon) > 1 else 0.0
        grid_res = round((lat_res + lon_res) / 2, 6) if (lat_res or lon_res) else 0.0

        if len(time_coords) >= 2:
            deltas_hours = np.diff(np.array([t.timestamp() for t in time_coords])) / 3600.0
            temporal_res = float(np.median(deltas_hours))
        else:
            temporal_res = 0.0

        uo_units = getattr(ds.variables["uo"], "units", "m s-1")
        vo_units = getattr(ds.variables["vo"], "units", "m s-1")
        title = getattr(ds, "title", path.stem)

        checksum, is_real_hash = _file_checksum(path)
        size_bytes = path.stat().st_size

        notes = "sha256 computed" if is_real_hash else "checksum is a size+mtime fallback digest"
        notes += "; read via netCDF4 (xarray hangs indefinitely on this exact file in this environment)"
        if time_series_status == TimeSeriesStatus.INSUFFICIENT:
            notes += f"; time_series_status=insufficient: only {n_time} timestep(s), cannot drive advection"

        return ForcingCube(
            cube_id=f"cmems-mc20-{path.stem}",
            source=ForcingSource.CMEMS_ANALYSIS,
            product_id=str(title),
            variables=[
                ForcingVariable(name="uo", unit=uo_units, standard_name=var_map["uo"]),
                ForcingVariable(name="vo", unit=vo_units, standard_name=var_map["vo"]),
            ],
            time_coords=time_coords,
            lat_coords=lat.tolist(),
            lon_coords=lon.tolist(),
            grid_resolution_deg=grid_res,
            temporal_resolution_hours=temporal_res,
            data_path=str(path),
            crs="EPSG:4326",
            bbox=bbox,
            time_range=(time_coords[0], time_coords[-1]),
            dataset_version=None,
            file_checksum=checksum,
            file_size_bytes=size_bytes,
            provenance=DataProvenance(
                source_id="cmems.real.mc20",
                adapter_id=adapter_id,
                license="Copernicus Marine Service License",
                raw_artifact_path=str(path),
                notes=notes,
            ),
            time_series_status=time_series_status,
            spatial_coverage_status=SpatialCoverageStatus.FULL,
        )
