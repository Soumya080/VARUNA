from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict

class SampleRef(BaseModel):
    sample_id: str
    content_hash: str
    
class DatasetSplit(BaseModel):
    train_ids: List[str]
    val_ids: List[str]
    test_ids: List[str]
    split_strategy: str       # "geographic" | "temporal" | "geographic_temporal"
    split_metadata: Dict      # region assignments, temporal boundaries

class DataQualityReport(BaseModel):
    total_samples: int
    valid_samples: int
    rejected_samples: int
    class_distribution: Dict[str, int]
    region_distribution: Dict[str, int]
    temporal_range: tuple[datetime, datetime]
    duplicate_count: int
    anomaly_count: int

class DatasetManifest(BaseModel):
    manifest_id: str
    dataset_name: str         # e.g. "netra_v1", "chhaya_v1"
    version: str
    created_at: datetime
    git_commit: str
    content_hash: str         # SHA-256 of all sample hashes
    samples: List[SampleRef]
    splits: DatasetSplit
    quality_report: DataQualityReport

class DatasetVersion(BaseModel):
    version: str
    manifest: DatasetManifest
    parent_version: Optional[str] = None
    changelog: str
    
    model_config = ConfigDict(extra="forbid")
