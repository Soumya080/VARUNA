from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, List, Optional
from datetime import datetime
from varuna_data_eng.schemas.quality import QualityState, DedupState
from varuna_data_eng.schemas.normalization import NormalizationRecord
from varuna_data_eng.schemas.provenance import DataProvenance

class ManifestEntry(BaseModel):
    sample_id: str
    scene_id: str
    content_hash: str
    split: str
    sensor: str
    region: str
    acquisition_date: datetime
    quality_state: QualityState
    dedup_state: DedupState
    file_paths: Dict[str, str]
    tile_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

class SplitManifest(BaseModel):
    strategy: str
    group_key: str
    split_counts: Dict[str, int]
    seed: int
    frozen_at: datetime

    model_config = ConfigDict(extra="forbid")

class DataQualityReport(BaseModel):
    total_samples: int
    passed: int
    warned: int
    rejected: int
    rejection_reasons: Dict[str, int]

    model_config = ConfigDict(extra="forbid")

class DatasetManifest(BaseModel):
    manifest_id: str
    dataset_id: str
    dataset_version: str
    created_at: datetime
    git_commit: str
    config_version: str
    content_hash: str
    samples: List[ManifestEntry]
    splits: SplitManifest
    normalization_stats: Optional[NormalizationRecord] = None
    quality_report: DataQualityReport
    pipeline_version: str
    source_datasets: List[str]
    sensor_distribution: Dict[str, int]
    license_summary: List[str]
    provenance: DataProvenance

    model_config = ConfigDict(extra="forbid")
