from enum import Enum
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Tuple
from datetime import datetime
from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.provenance import DataProvenance

class ForcingSource(str, Enum):
    ERA5 = "ERA5"
    CMEMS_ANALYSIS = "CMEMS_ANALYSIS"
    CMEMS_REANALYSIS = "CMEMS_REANALYSIS"

class ForcingVariable(BaseModel):
    name: str
    unit: str
    standard_name: Optional[str] = None
    fill_value: Optional[float] = None

    model_config = ConfigDict(extra="forbid")

class ForcingCube(BaseModel):
    cube_id: str
    source: ForcingSource
    product_id: str
    variables: List[ForcingVariable]
    time_coords: List[datetime]
    lat_coords: List[float]
    lon_coords: List[float]
    grid_resolution_deg: float
    temporal_resolution_hours: float
    data_path: str
    crs: str
    bbox: BBox
    time_range: Tuple[datetime, datetime]
    dataset_version: Optional[str] = None
    file_checksum: str
    file_size_bytes: int
    provenance: DataProvenance

    model_config = ConfigDict(extra="forbid")
