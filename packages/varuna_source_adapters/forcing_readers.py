"""
VARUNA GRID — Real ERA5 / CMEMS file readers.

READ-ONLY. Never modifies the source GRIB/NetCDF file. Each reader here
opens an existing local file and builds a validated ForcingCube; it does
not fetch, download, or fabricate anything.

These are the only two functions that know how to turn a raw forcing file
into the canonical ForcingCube contract. `era5.py` and `copernicus_marine.py`
(the SourceAdapter implementations) call these and are otherwise thin.

Both readers set `time_series_status` and `spatial_coverage_status`
explicitly rather than defaulting to "looks fine" — this is where the two
audit findings (CMEMS single-timestep snapshots; ERA5's three GRIB chunks
spanning three different bounding boxes) become structured data instead of
a comment someone has to remember to check.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.forcing import (
    ForcingCube,
    ForcingSource,
    ForcingVariable,
    SpatialCoverageStatus,
    TimeSeriesStatus,
)
from varuna_data_eng.schemas.provenance import DataProvenance


def _file_checksum(path: Path, limit_bytes: int = 8 * 1024 * 1024) -> tuple[str, bool]:
    """sha256 for files under `limit_bytes`; above it, hash is skipped (large
    GRIB/NetCDF forcing files are not worth a multi-GB hash on every read) and
    a size+mtime fallback digest is returned instead. Returns (digest, is_real_sha256)."""
    size = path.stat().st_size
    if size > limit_bytes:
        fallback = f"size:{size}:mtime:{int(path.stat().st_mtime)}"
        return hashlib.sha256(fallback.encode()).hexdigest(), False
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest(), True


def read_era5_grib(
    path: Path,
    *,
    reference_bbox: BBox | None = None,
    adapter_id: str = "era5.real",
) -> ForcingCube:
    """Build a ForcingCube from a real ERA5 GRIB1 file containing
    10m_u_component_of_wind (u10) and 10m_v_component_of_wind (v10).

    Raises ImportError with a clear message if cfgrib/eccodes are not
    installed — never silently falls back to something else.

    If `reference_bbox` is given and this file's bbox does not match it
    (the known ERA5 3-chunk-3-bbox problem), spatial_coverage_status is set
    to `partial` and the cube's bbox is the intersection of the two, not a
    union — a caller must never receive a bbox promising coverage this file
    does not have.
    """
    try:
        import cfgrib  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "cfgrib/eccodes are required to read ERA5 GRIB files and are not "
            "installed in this environment. Install with "
            "`pip install cfgrib eccodes` (redirect PIP_CACHE_DIR off a full "
            "C: drive if applicable). Refusing to fabricate forcing data."
        ) from e

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ERA5 GRIB file not found: {path}")

    ds = xr.open_dataset(path, engine="cfgrib")
    try:
        var_map = {"u10": "10m_u_component_of_wind", "v10": "10m_v_component_of_wind"}
        missing = [v for v in var_map if v not in ds.data_vars]
        if missing:
            raise ValueError(
                f"ERA5 file {path} is missing required variable(s) {missing}; "
                f"found {list(ds.data_vars)}. Refusing to build a partial cube."
            )

        lat = np.asarray(ds["latitude"].values, dtype=float)
        lon = np.asarray(ds["longitude"].values, dtype=float)
        if lat.ndim != 1 or lon.ndim != 1:
            raise ValueError(f"ERA5 file {path} has a non-1D coordinate grid; unsupported.")
        if not (np.all(np.diff(lat) > 0) or np.all(np.diff(lat) < 0)):
            raise ValueError(f"ERA5 file {path} latitude coordinate is not monotonic.")
        if not (np.all(np.diff(lon) > 0) or np.all(np.diff(lon) < 0)):
            raise ValueError(f"ERA5 file {path} longitude coordinate is not monotonic.")

        if "time" in ds["u10"].dims:
            time_vals = np.atleast_1d(ds["time"].values)
        elif "valid_time" in ds.coords:
            time_vals = np.atleast_1d(ds["valid_time"].values)
        else:
            time_vals = np.array([ds.attrs.get("GRIB_referenceDate")], dtype="datetime64[ns]")
        time_coords = [
            datetime.fromtimestamp(t.astype("datetime64[s]").astype(int), tz=UTC)
            for t in np.atleast_1d(time_vals)
        ]
        if len(time_coords) < 2:
            time_series_status = TimeSeriesStatus.INSUFFICIENT
        else:
            time_series_status = TimeSeriesStatus.SUFFICIENT

        lat_min, lat_max = float(lat.min()), float(lat.max())
        lon_min, lon_max = float(lon.min()), float(lon.max())
        file_bbox = BBox(min_lon=lon_min, min_lat=lat_min, max_lon=lon_max, max_lat=lat_max)

        spatial_status = SpatialCoverageStatus.FULL
        out_bbox = file_bbox
        if reference_bbox is not None:
            ix_min_lon = max(file_bbox.min_lon, reference_bbox.min_lon)
            ix_min_lat = max(file_bbox.min_lat, reference_bbox.min_lat)
            ix_max_lon = min(file_bbox.max_lon, reference_bbox.max_lon)
            ix_max_lat = min(file_bbox.max_lat, reference_bbox.max_lat)
            if ix_min_lon >= ix_max_lon or ix_min_lat >= ix_max_lat:
                spatial_status = SpatialCoverageStatus.UNAVAILABLE
                out_bbox = file_bbox  # keep something valid for the pydantic model
            elif (
                abs(ix_min_lon - file_bbox.min_lon) > 1e-6
                or abs(ix_max_lon - file_bbox.max_lon) > 1e-6
                or abs(ix_min_lat - file_bbox.min_lat) > 1e-6
                or abs(ix_max_lat - file_bbox.max_lat) > 1e-6
            ):
                spatial_status = SpatialCoverageStatus.PARTIAL
                out_bbox = BBox(
                    min_lon=ix_min_lon, min_lat=ix_min_lat,
                    max_lon=ix_max_lon, max_lat=ix_max_lat,
                )

        lat_res = float(abs(np.median(np.diff(lat))))
        lon_res = float(abs(np.median(np.diff(lon))))
        grid_res = round((lat_res + lon_res) / 2, 6)

        if len(time_coords) >= 2:
            deltas_hours = np.diff(
                np.array([t.timestamp() for t in time_coords])
            ) / 3600.0
            temporal_res = float(np.median(deltas_hours))
        else:
            temporal_res = 0.0

        checksum, is_real_hash = _file_checksum(path)
        size_bytes = path.stat().st_size

        return ForcingCube(
            cube_id=f"era5-{path.stem}",
            source=ForcingSource.ERA5,
            product_id="reanalysis-era5-single-levels:10m_wind",
            variables=[
                ForcingVariable(name="u10", unit="m s**-1", standard_name=var_map["u10"]),
                ForcingVariable(name="v10", unit="m s**-1", standard_name=var_map["v10"]),
            ],
            time_coords=time_coords,
            lat_coords=lat.tolist(),
            lon_coords=lon.tolist(),
            grid_resolution_deg=grid_res,
            temporal_resolution_hours=temporal_res,
            data_path=str(path),
            crs="EPSG:4326",
            bbox=out_bbox,
            time_range=(time_coords[0], time_coords[-1]),
            dataset_version=None,
            file_checksum=checksum,
            file_size_bytes=size_bytes,
            provenance=DataProvenance(
                source_id="era5.real",
                adapter_id=adapter_id,
                license="Copernicus Climate Change Service (C3S) License",
                raw_artifact_path=str(path),
                notes=(
                    "sha256 computed" if is_real_hash
                    else "checksum is a size+mtime fallback digest (file exceeds hash size limit)"
                ),
            ),
            time_series_status=time_series_status,
            spatial_coverage_status=spatial_status,
        )
    finally:
        ds.close()


def read_cmems_netcdf(path: Path, *, adapter_id: str = "cmems.real") -> ForcingCube:
    """Build a ForcingCube from a real CMEMS NetCDF file containing eastward
    (uo) and northward (vo) surface current components.

    A single-timestep file is not treated as an error — it is a legitimate,
    honestly-labelled ForcingCube with time_series_status=INSUFFICIENT.
    Callers (CubeBackedCurrentField) must refuse to use it for advection;
    that refusal happens at `ForcingCube.assert_usable_for_advection()`,
    not here.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CMEMS NetCDF file not found: {path}")

    ds = xr.open_dataset(path)
    try:
        var_map = {"uo": "eastward_sea_water_velocity", "vo": "northward_sea_water_velocity"}
        missing = [v for v in var_map if v not in ds.data_vars]
        if missing:
            raise ValueError(
                f"CMEMS file {path} is missing required variable(s) {missing}; "
                f"found {list(ds.data_vars)}. Refusing to build a partial cube."
            )

        lat_name = "latitude" if "latitude" in ds.coords else "lat"
        lon_name = "longitude" if "longitude" in ds.coords else "lon"
        lat = np.asarray(ds[lat_name].values, dtype=float)
        lon = np.asarray(ds[lon_name].values, dtype=float)

        n_time = ds.sizes.get("time", 1)
        if "time" in ds.coords:
            time_vals = np.atleast_1d(ds["time"].values)
            time_coords = [
                datetime.fromtimestamp(
                    np.datetime64(t, "s").astype(int), tz=UTC
                )
                for t in time_vals
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
            deltas_hours = np.diff(
                np.array([t.timestamp() for t in time_coords])
            ) / 3600.0
            temporal_res = float(np.median(deltas_hours))
        else:
            temporal_res = 0.0

        checksum, is_real_hash = _file_checksum(path)
        size_bytes = path.stat().st_size

        return ForcingCube(
            cube_id=f"cmems-{path.stem}",
            source=ForcingSource.CMEMS_ANALYSIS,
            product_id=str(ds.attrs.get("title", path.stem)),
            variables=[
                ForcingVariable(name="uo", unit="m s-1", standard_name=var_map["uo"]),
                ForcingVariable(name="vo", unit="m s-1", standard_name=var_map["vo"]),
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
                source_id="cmems.real",
                adapter_id=adapter_id,
                license="Copernicus Marine Service License",
                raw_artifact_path=str(path),
                notes=(
                    ("sha256 computed" if is_real_hash else "checksum is a size+mtime fallback digest")
                    + (f"; time_series_status=insufficient: only {n_time} timestep(s) present, "
                       f"cannot drive advection" if time_series_status == TimeSeriesStatus.INSUFFICIENT
                       else "")
                ),
            ),
            time_series_status=time_series_status,
            spatial_coverage_status=SpatialCoverageStatus.FULL,
        )
    finally:
        ds.close()


def load_era5_wind_arrays(cube: ForcingCube) -> tuple[np.ndarray, np.ndarray]:
    """Load the raw (n_time, n_lat, n_lon) u10/v10 arrays backing `cube` from
    its own `data_path`, in the exact coordinate order `read_era5_grib`
    stored (`cube.lat_coords`/`cube.lon_coords`) — this is what
    `CubeBackedWindField.load_arrays()` requires. Read-only; opens the same
    file `read_era5_grib` already validated, does not fabricate or resample.
    """
    ds = xr.open_dataset(cube.data_path, engine="netcdf4")
    try:
        u = np.asarray(ds["u10"].values, dtype=float)
        v = np.asarray(ds["v10"].values, dtype=float)
        return u, v
    finally:
        ds.close()


def load_cmems_current_arrays(cube: ForcingCube) -> tuple[np.ndarray, np.ndarray]:
    """Load the raw (n_time, n_lat, n_lon) uo/vo arrays backing `cube` from
    its own `data_path`, in the exact coordinate order `read_cmems_netcdf`
    stored. CMEMS Copernicus Marine files carry a `depth` dimension even for
    surface fields (single-level `depth=0`, sized 1 here) —
    `CubeBackedCurrentField.load_arrays()` expects a plain (n_time, n_lat,
    n_lon) grid, so the length-1 depth axis is squeezed here, not silently
    reshaped or averaged: `assert cube's depth dim is exactly 1` before
    squeezing, so a genuinely multi-level file would raise rather than
    silently pick a level.
    """
    ds = xr.open_dataset(cube.data_path, engine="netcdf4")
    try:
        u_da, v_da = ds["uo"], ds["vo"]
        if "depth" in u_da.dims:
            depth_axis = u_da.dims.index("depth")
            if ds.sizes["depth"] != 1:
                raise ValueError(
                    f"CMEMS file {cube.data_path} has {ds.sizes['depth']} depth "
                    f"levels; load_cmems_current_arrays only supports the "
                    f"single-level surface case and refuses to guess which "
                    f"level to use."
                )
            u = np.squeeze(np.asarray(u_da.values, dtype=float), axis=depth_axis)
            v = np.squeeze(np.asarray(v_da.values, dtype=float), axis=depth_axis)
        else:
            u = np.asarray(u_da.values, dtype=float)
            v = np.asarray(v_da.values, dtype=float)
        return u, v
    finally:
        ds.close()
