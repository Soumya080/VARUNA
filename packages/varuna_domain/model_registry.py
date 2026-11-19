from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Protocol
import uuid

class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    RETIRED = "retired"

class ModelVersion(BaseModel):
    model_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model_name: str
    version: str
    artifact_path: str
    dataset_version: str
    training_config: dict[str, Any]
    evaluation_metrics: dict[str, Any] = Field(default_factory=dict)
    git_commit: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: ModelStatus = ModelStatus.CANDIDATE
    approved_by: Optional[str] = None
    deployed_at: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid")

class ModelRegistry(Protocol):
    def register(self, model_name: str, version: str, artifact_path: str, dataset_version: str, training_config: dict[str, Any], git_commit: str) -> ModelVersion:
        ...
        
    def get_latest(self, model_name: str) -> Optional[ModelVersion]:
        ...
        
    def get_version(self, model_name: str, version: str) -> Optional[ModelVersion]:
        ...
        
    def list_versions(self, model_name: str) -> List[ModelVersion]:
        ...
        
    def is_registered(self, model_name: str, version: str) -> bool:
        ...

    def update_status(self, model_name: str, version: str, status: ModelStatus, approved_by: Optional[str] = None) -> ModelVersion:
        ...

class InMemoryModelRegistry:
    def __init__(self):
        self._store: Dict[str, List[ModelVersion]] = {}

    def register(self, model_name, version, artifact_path, dataset_version, training_config, git_commit):
        mv = ModelVersion(
            model_name=model_name, 
            version=version, 
            artifact_path=artifact_path, 
            dataset_version=dataset_version,
            training_config=training_config,
            git_commit=git_commit
        )
        self._store.setdefault(model_name, []).append(mv)
        return mv

    def get_latest(self, model_name):
        versions = self._store.get(model_name, [])
        return versions[-1] if versions else None

    def get_version(self, model_name, version):
        for mv in self._store.get(model_name, []):
            if mv.version == version:
                return mv
        return None

    def list_versions(self, model_name):
        return list(self._store.get(model_name, []))

    def is_registered(self, model_name, version):
        return self.get_version(model_name, version) is not None

    def update_status(self, model_name: str, version: str, status: ModelStatus, approved_by: Optional[str] = None) -> ModelVersion:
        mv = self.get_version(model_name, version)
        if not mv:
            raise ValueError(f"Model {model_name} version {version} not found")
            
        if status == ModelStatus.APPROVED and not approved_by:
            raise ValueError("approved_by must be set when status is APPROVED")
            
        if status == ModelStatus.DEPLOYED and mv.status not in (ModelStatus.APPROVED, ModelStatus.DEPLOYED):
            raise ValueError("Model must be APPROVED before DEPLOYED")

        mv.status = status
        if status == ModelStatus.APPROVED:
            mv.approved_by = approved_by
        elif status == ModelStatus.DEPLOYED:
            mv.deployed_at = datetime.now(timezone.utc)
            
        return mv
