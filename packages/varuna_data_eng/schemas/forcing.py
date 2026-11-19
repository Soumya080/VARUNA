from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.provenance import DataProvenance


class ForcingSource(str, Enum):
    ERA5 = "ERA5"
    CMEMS_ANALYSIS = "CMEMS_ANALYSIS"
    CMEMS_REANALYSIS = "CMEMS_REANALYSIS"

class ForcingVariable(BaseModel):
    name: str
    unit: str
    standard_name: str | None = None
    fill_value: float | None = None

    model_config = ConfigDict(extra="forbid")

class TimeSeriesStatus(str, Enum):
    """Whether this cube's time axis is actually usable for time-dependent
    physics (advection). A single timestep is not — see CMEMS snapshots in
    data/raw/cmems/, which must never be silently treated as sufficient."""
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    UNAVAILABLE = "unavailable"

class SpatialCoverageStatus(str, Enum):
    """Whether the cube's spatial grid is one consistent domain. ERA5's three
    local GRIB chunks span three different bounding boxes; a cube built
    across them without reconciling to their intersection is `partial`,
    never silently `full`."""
    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"

class ForcingCube(BaseModel):
    cube_id: str
    source: ForcingSource
    product_id: str
    variables: list[ForcingVariable]
    time_coords: list[datetime]
    lat_coords: list[float]
    lon_coords: list[float]
    grid_resolution_deg: float
    temporal_resolution_hours: float
    data_path: str
    crs: str
    bbox: BBox
    time_range: tuple[datetime, datetime]
    dataset_version: str | None = None
    file_checksum: str
    file_size_bytes: int
    provenance: DataProvenance

    # Honest-coverage flags. Both required (no silent default to "sufficient"/
    # "full") so a builder must explicitly decide these rather than let a
    # cube pass through unexamined. See TimeSeriesStatus/SpatialCoverageStatus
    # docstrings for the concrete cases (CMEMS single-timestep, ERA5 3-bbox
    # split) that motivated making this data rather than a comment.
    time_series_status: TimeSeriesStatus
    spatial_coverage_status: SpatialCoverageStatus

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_time_series_status_consistency(self) -> "ForcingCube":
        n_steps = len(self.time_coords)
        if n_steps <= 1 and self.time_series_status == TimeSeriesStatus.SUFFICIENT:
            raise ValueError(
                f"ForcingCube {self.cube_id!r} has {n_steps} time step(s) "
                f"but claims time_series_status=sufficient; a single "
                f"timestep cannot be marked sufficient for advection."
            )
        if not self.lat_coords or not self.lon_coords:
            raise ValueError(f"ForcingCube {self.cube_id!r} has an empty spatial grid.")
        return self

    def assert_usable_for_advection(self) -> None:
        """Fail closed. Raise rather than let a caller (PRATIVARTAN/PRAVAAH)
        silently extrapolate from an insufficient or unavailable cube."""
        if self.time_series_status != TimeSeriesStatus.SUFFICIENT:
            raise ValueError(
                f"ForcingCube {self.cube_id!r} has time_series_status="
                f"{self.time_series_status.value!r}; cannot drive "
                f"time-dependent advection. Refusing rather than "
                f"extrapolating from a single timestep."
            )
        if self.spatial_coverage_status == SpatialCoverageStatus.UNAVAILABLE:
            raise ValueError(
                f"ForcingCube {self.cube_id!r} has "
                f"spatial_coverage_status=unavailable; no usable grid."
            )
