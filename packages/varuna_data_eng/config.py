import os
from pydantic import BaseModel, Field

class PipelineConfig(BaseModel):
    data_mode: str = Field(default_factory=lambda: os.getenv("VARUNA_DATA_MODE", "synthetic"))
    tile_size: int = 512
    stride: int = 512
    min_valid_fraction: float = 0.8
    min_label_fraction: float = 0.0
    min_oil_fraction: float = 0.01
    output_format: str = "npy"
