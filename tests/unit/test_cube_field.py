"""Tests for CubeBackedCurrentField / CubeBackedWindField — the ForcingCube
seam into PRATIVARTAN. Verifies fail-closed behavior on insufficient time
series and out-of-domain queries, and correct interpolation on a synthetic
in-memory cube (no real ERA5/CMEMS file I/O — that's covered separately)."""
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.forcing import (
    ForcingCube,
    ForcingSource,
    ForcingVariable,
    SpatialCoverageStatus,
    TimeSeriesStatus,
)
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_prativartan.cube_field import (
    CubeBackedCurrentField,
    CubeBackedWindField,
    OutOfDomainError,
)


def _make_cube(var_names, n_time=3, time_series_status=TimeSeriesStatus.SUFFICIENT):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(hours=i) for i in range(n_time)]
    return ForcingCube(
        cube_id="test-cube",
        source=ForcingSource.ERA5,
        product_id="test",
        variables=[ForcingVariable(name=n, unit="m/s") for n in var_names],
        time_coords=times,
        lat_coords=[0.0, 10.0],
        lon_coords=[0.0, 10.0],
        grid_resolution_deg=10.0,
        temporal_resolution_hours=1.0,
        data_path="/dev/null",
        crs="EPSG:4326",
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=10.0, max_lat=10.0),
        time_range=(times[0], times[-1]),
        file_checksum="deadbeef",
        file_size_bytes=1,
        provenance=DataProvenance(source_id="test", adapter_id="test", license="test"),
        time_series_status=time_series_status,
        spatial_coverage_status=SpatialCoverageStatus.FULL,
    )


def test_current_field_rejects_insufficient_cube_at_construction():
    cube = _make_cube(["uo", "vo"], n_time=1, time_series_status=TimeSeriesStatus.INSUFFICIENT)
    with pytest.raises(ValueError, match="insufficient"):
        CubeBackedCurrentField(cube)


def test_current_field_rejects_missing_variable():
    cube = _make_cube(["uo"], n_time=3)  # missing vo
    with pytest.raises(ValueError, match="vo"):
        CubeBackedCurrentField(cube)


def test_wind_field_uses_u10_v10():
    cube = _make_cube(["u10", "v10"], n_time=3)
    field = CubeBackedWindField(cube)
    u_grid = np.ones((3, 2, 2)) * 5.0
    v_grid = np.ones((3, 2, 2)) * 2.0
    field.load_arrays(u_grid, v_grid)
    u, v = field.velocity_at(np.array([5.0]), np.array([5.0]), t_hours=0.0)
    assert np.isclose(u[0], 5.0)
    assert np.isclose(v[0], 2.0)


def test_query_without_loaded_arrays_raises():
    cube = _make_cube(["uo", "vo"], n_time=3)
    field = CubeBackedCurrentField(cube)
    with pytest.raises(RuntimeError, match="load_arrays"):
        field.velocity_at(np.array([5.0]), np.array([5.0]), t_hours=0.0)


def test_out_of_domain_spatial_raises():
    cube = _make_cube(["uo", "vo"], n_time=3)
    field = CubeBackedCurrentField(cube)
    field.load_arrays(np.zeros((3, 2, 2)), np.zeros((3, 2, 2)))
    with pytest.raises(OutOfDomainError):
        field.velocity_at(np.array([999.0]), np.array([5.0]), t_hours=0.0)


def test_out_of_domain_temporal_raises():
    cube = _make_cube(["uo", "vo"], n_time=3)
    field = CubeBackedCurrentField(cube)
    field.load_arrays(np.zeros((3, 2, 2)), np.zeros((3, 2, 2)))
    with pytest.raises(OutOfDomainError):
        field.velocity_at(np.array([5.0]), np.array([5.0]), t_hours=99999.0)


def test_bilinear_interpolation_midpoint():
    cube = _make_cube(["uo", "vo"], n_time=3)
    field = CubeBackedCurrentField(cube)
    # corners: (lat=0,lon=0)=0, (lat=0,lon=10)=10, (lat=10,lon=0)=20, (lat=10,lon=10)=30
    u_grid = np.array([[[0.0, 10.0], [20.0, 30.0]]] * 3)
    v_grid = np.zeros((3, 2, 2))
    field.load_arrays(u_grid, v_grid)
    u, _ = field.velocity_at(np.array([5.0]), np.array([5.0]), t_hours=0.0)
    assert np.isclose(u[0], 15.0, atol=1e-6)
