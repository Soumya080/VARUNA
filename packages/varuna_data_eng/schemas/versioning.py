from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from varuna_data_eng.schemas.manifest import DatasetManifest

class DatasetVersion(BaseModel):
    dataset_id: str
    version: str
    manifest: DatasetManifest
    parent_version: Optional[str] = None
    changelog: str
    created_at: datetime
    git_commit: str
    config_hash: str
    seed: int = 42

    model_config = ConfigDict(extra="forbid")

class TrainingRunRecord(BaseModel):
    experiment_id: str
    dataset_version: str
    model_version: str
    git_commit: str
    config_version: str
    seed: int
    normalization_checksum: str
    split_manifest_checksum: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid")
