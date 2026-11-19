from enum import Enum
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Dict, List, Optional
from datetime import datetime
from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.provenance import DataProvenance

class SARSensor(str, Enum):
    SENTINEL_1 = "SENTINEL_1"
    NISAR_S = "NISAR_S"
    RISAT_2B = "RISAT_2B"

class SARBand(str, Enum):
    C = "C"
    L = "L"
    X = "X"
    S = "S"

class Polarization(str, Enum):
    VV = "VV"
    VH = "VH"
    HH = "HH"
    HV = "HV"

class ChannelMeta(BaseModel):
    name: str
    unit: str
    dtype: str
    nodata_value: Optional[float] = None
    valid_range: Optional[List[float]] = None

    model_config = ConfigDict(extra="forbid")

class CanonicalSAR(BaseModel):
    scene_id: str
    source_dataset: str
    sensor: SARSensor
    platform: str
    band: SARBand
    polarizations: List[Polarization]
    product_type: str
    processing_level: str
    processing_baseline: Optional[str] = None
    acquisition_time: datetime
    resolution_m: float
    pixel_spacing_m: float
    width_px: int
    height_px: int
    crs: str
    bbox: BBox
    channels: Dict[str, ChannelMeta]
    data_path: str
    quality_mask_path: Optional[str] = None
    file_checksum: str
    file_size_bytes: int
    provenance: DataProvenance
    metadata: Dict[str, str] = {}

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_sensor_band(self) -> 'CanonicalSAR':
        expected_bands = {
            SARSensor.SENTINEL_1: SARBand.C,
            SARSensor.NISAR_S: SARBand.S,
            SARSensor.RISAT_2B: SARBand.X
        }
        if self.sensor in expected_bands:
            if self.band != expected_bands[self.sensor]:
                raise ValueError(f"Invalid band {self.band} for sensor {self.sensor}. Expected {expected_bands[self.sensor]}")
        return self
