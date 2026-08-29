"""Tests for the real ERA5/CMEMS file readers. Uses the actual local files
under data/raw/ when present (opening one file is cheap; this does not scan
the full corpus). Skips cleanly when a dependency or the data file is absent
— this repo's raw data is gitignored, and cfgrib/eccodes may not be
installed in every environment."""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ERA5_DIR = REPO_ROOT / "data" / "raw" / "era5"
CMEMS_DIR = REPO_ROOT / "data" / "raw" / "cmems"

cfgrib = pytest.importorskip(
    "cfgrib", reason="cfgrib not installed; ERA5 reader tests need it"
)

from varuna_data_eng.schemas.forcing import SpatialCoverageStatus, TimeSeriesStatus  # noqa: E402
from varuna_source_adapters.forcing_readers import read_cmems_netcdf, read_era5_grib  # noqa: E402


def _first(pattern: str, root: Path) -> Path | None:
    matches = sorted(root.glob(pattern)) if root.exists() else []
    return matches[0] if matches else None


@pytest.mark.skipif(not ERA5_DIR.exists(), reason="no local ERA5 data")
def test_read_era5_grib_real_file():
    grib_file = _first("*.grib", ERA5_DIR)
    if grib_file is None:
        pytest.skip("no .grib files present under data/raw/era5")

    cube = read_era5_grib(grib_file)

    var_names = {v.name for v in cube.variables}
    assert var_names == {"u10", "v10"}
    assert cube.crs == "EPSG:4326"
    assert len(cube.lat_coords) > 1
    assert len(cube.lon_coords) > 1
    # This repo's known state: hourly, continuous, so any single chunk should
    # have plenty of timesteps and be SUFFICIENT.
    assert cube.time_series_status == TimeSeriesStatus.SUFFICIENT
    assert cube.spatial_coverage_status == SpatialCoverageStatus.FULL  # no reference_bbox given
    assert cube.bbox.min_lat >= 0 and cube.bbox.max_lat <= 90  # Indian-waters domain
    assert cube.file_checksum


@pytest.mark.skipif(not ERA5_DIR.exists(), reason="no local ERA5 data")
def test_read_era5_grib_reference_bbox_marks_partial():
    from varuna_contracts.schemas import BBox
    grib_file = _first("*.grib", ERA5_DIR)
    if grib_file is None:
        pytest.skip("no .grib files present under data/raw/era5")

    # A reference bbox known to be smaller than any single file's coverage —
    # forces spatial_coverage_status away from FULL.
    tiny_ref = BBox(min_lon=71.0, min_lat=9.0, max_lon=72.0, max_lat=10.0)
    cube = read_era5_grib(grib_file, reference_bbox=tiny_ref)
    assert cube.spatial_coverage_status in (
        SpatialCoverageStatus.PARTIAL, SpatialCoverageStatus.FULL
    )


@pytest.mark.skipif(not CMEMS_DIR.exists(), reason="no local CMEMS data")
def test_read_cmems_netcdf_reports_insufficient_for_single_timestep():
    nc_file = _first("**/*.nc", CMEMS_DIR)
    if nc_file is None:
        pytest.skip("no .nc files present under data/raw/cmems")

    cube = read_cmems_netcdf(nc_file)

    var_names = {v.name for v in cube.variables}
    assert var_names == {"uo", "vo"}
    # This repo's known state: both CMEMS files are single-timestep snapshots.
    assert cube.time_series_status == TimeSeriesStatus.INSUFFICIENT
    with pytest.raises(ValueError, match="insufficient"):
        cube.assert_usable_for_advection()
