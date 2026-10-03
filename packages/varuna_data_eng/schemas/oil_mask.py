from enum import Enum
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Dict, Optional
from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.provenance import DataProvenance

class OilLabelClass(str, Enum):
    OIL = "OIL"
    LOOK_ALIKE = "LOOK_ALIKE"
    BACKGROUND = "BACKGROUND"
    UNKNOWN = "UNKNOWN"

class OilMask(BaseModel):
    mask_id: str
    scene_id: str
    label_class: OilLabelClass
    mask_path: str
    mask_crs: str
    mask_bbox: BBox
    mask_resolution_m: float
    mask_width_px: int
    mask_height_px: int
    annotation_source: str
    annotation_version: str
    annotator_count: Optional[int] = None
    confidence: Optional[float] = None
    class_counts: Dict[str, int]
    file_checksum: str
    provenance: DataProvenance

    model_config = ConfigDict(extra="forbid")

    @field_validator("mask_width_px", "mask_height_px")
    @classmethod
    def _dims_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("mask dimensions must be positive")
        return v

    @field_validator("mask_resolution_m")
    @classmethod
    def _resolution_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("mask_resolution_m must be positive")
        return v
