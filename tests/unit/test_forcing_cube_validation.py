"""Tests for ForcingCube's honest-coverage status fields and fail-closed
`assert_usable_for_advection()`. See packages/varuna_data_eng/schemas/forcing.py."""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.forcing import (
    ForcingCube,
    ForcingSource,
    ForcingVariable,
    SpatialCoverageStatus,
    TimeSeriesStatus,
)
from varuna_data_eng.schemas.provenance import DataProvenance


def _bbox():
    return BBox(min_lon=70.0, min_lat=5.0, max_lon=85.0, max_lat=20.0)


def _prov():
    return DataProvenance(source_id="test", adapter_id="test", license="test")


def _cube(*, n_time: int, time_series_status: TimeSeriesStatus,
          spatial_coverage_status: SpatialCoverageStatus = SpatialCoverageStatus.FULL) -> ForcingCube:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(hours=i) for i in range(n_time)]
    return ForcingCube(
        cube_id="test-cube",
        source=ForcingSource.CMEMS_ANALYSIS,
        product_id="test",
        variables=[ForcingVariable(name="uo", unit="m/s"), ForcingVariable(name="vo", unit="m/s")],
        time_coords=times,
        lat_coords=[5.0, 10.0, 15.0, 20.0],
        lon_coords=[70.0, 75.0, 80.0, 85.0],
        grid_resolution_deg=5.0,
        temporal_resolution_hours=1.0,
        data_path="/dev/null",
        crs="EPSG:4326",
        bbox=_bbox(),
        time_range=(times[0], times[-1]),
        file_checksum="deadbeef",
        file_size_bytes=100,
        provenance=_prov(),
        time_series_status=time_series_status,
        spatial_coverage_status=spatial_coverage_status,
    )


def test_single_timestep_cannot_claim_sufficient():
    with pytest.raises(ValidationError):
        _cube(n_time=1, time_series_status=TimeSeriesStatus.SUFFICIENT)


def test_single_timestep_insufficient_constructs_fine():
    cube = _cube(n_time=1, time_series_status=TimeSeriesStatus.INSUFFICIENT)
    assert cube.time_series_status == TimeSeriesStatus.INSUFFICIENT


def test_multi_timestep_sufficient_constructs_fine():
    cube = _cube(n_time=5, time_series_status=TimeSeriesStatus.SUFFICIENT)
    assert cube.time_series_status == TimeSeriesStatus.SUFFICIENT


def test_assert_usable_for_advection_raises_on_insufficient():
    cube = _cube(n_time=1, time_series_status=TimeSeriesStatus.INSUFFICIENT)
    with pytest.raises(ValueError, match="insufficient"):
        cube.assert_usable_for_advection()


def test_assert_usable_for_advection_raises_on_unavailable_spatial():
    cube = _cube(n_time=5, time_series_status=TimeSeriesStatus.SUFFICIENT,
                 spatial_coverage_status=SpatialCoverageStatus.UNAVAILABLE)
    with pytest.raises(ValueError, match="spatial_coverage_status"):
        cube.assert_usable_for_advection()


def test_assert_usable_for_advection_passes_when_sufficient_and_full():
    cube = _cube(n_time=5, time_series_status=TimeSeriesStatus.SUFFICIENT,
                 spatial_coverage_status=SpatialCoverageStatus.FULL)
    cube.assert_usable_for_advection()  # must not raise


def test_partial_spatial_coverage_still_usable_for_advection():
    cube = _cube(n_time=5, time_series_status=TimeSeriesStatus.SUFFICIENT,
                 spatial_coverage_status=SpatialCoverageStatus.PARTIAL)
    cube.assert_usable_for_advection()  # partial spatial != unavailable; must not raise


def test_extra_forbid_rejects_unknown_field():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        ForcingCube(
            cube_id="x", source=ForcingSource.ERA5, product_id="x",
            variables=[], time_coords=[base, base + timedelta(hours=1)],
            lat_coords=[1.0, 2.0], lon_coords=[1.0, 2.0],
            grid_resolution_deg=1.0, temporal_resolution_hours=1.0,
            data_path="x", crs="EPSG:4326", bbox=_bbox(),
            time_range=(base, base), file_checksum="x", file_size_bytes=1,
            provenance=_prov(), time_series_status=TimeSeriesStatus.SUFFICIENT,
            spatial_coverage_status=SpatialCoverageStatus.FULL,
            not_a_real_field="oops",
        )
