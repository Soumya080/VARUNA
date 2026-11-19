from pydantic import BaseModel, ConfigDict
from typing import Dict
from datetime import datetime

class ChannelStats(BaseModel):
    mean: float
    std: float
    min: float
    max: float
    p2: float
    p98: float

    model_config = ConfigDict(extra="forbid")

class NormalizationRecord(BaseModel):
    dataset_version: str
    sensor: str
    channels: Dict[str, ChannelStats]
    method: str
    computed_from_split: str = "train"
    n_samples: int
    computed_at: datetime
    checksum: str

    model_config = ConfigDict(extra="forbid")
