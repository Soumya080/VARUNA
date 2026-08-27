from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from varuna_contracts.schemas import BBox

class DataProvenance(BaseModel):
    source_id: str
    source_version: Optional[str] = None
    download_url: Optional[str] = None
    download_time: Optional[datetime] = None
    adapter_id: str
    original_filename: Optional[str] = None
    original_crs: Optional[str] = None
    original_resolution_m: Optional[float] = None
    license: str
    citation: Optional[str] = None
    raw_artifact_path: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class PixelWindow(BaseModel):
    """Location of a tile within its parent scene, in pixel space."""
    x_offset: int
    y_offset: int
    width: int
    height: int

    model_config = ConfigDict(extra="forbid")

class TileRecord(BaseModel):
    """Provenance-complete record of one model-ready tile cut from a GOLD scene.

    Every field a tile is trained/evaluated with must be traceable back to its
    parent scene, the split it belongs to, and the dataset that produced it —
    a tile can never outlive that lineage.
    """
    tile_id: str
    parent_scene_id: str
    split: str
    sensor: str
    source: str
    row: int
    column: int
    pixel_window: PixelWindow
    bbox: Optional[BBox] = None
    provenance: DataProvenance
    data: Optional[bytes] = None  # raw tile payload; may be stored out-of-band instead

    model_config = ConfigDict(extra="forbid")
