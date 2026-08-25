"""
VARUNA GRID — PRAMAN: Provenance + Artifact Manager.

In-memory implementation for local demo. No MinIO required.
"""
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


class ArtifactRecord:
    def __init__(self, artifact_id: str, artifact_type: str,
                 case_id: str, produced_by: str, data: Any):
        self.artifact_id = artifact_id
        self.artifact_type = artifact_type
        self.case_id = case_id
        self.produced_by = produced_by
        self.data = data
        self.created_at = datetime.now(timezone.utc)
        self.content_hash = str(hash(str(data)))[:16]


class PramanService:
    """In-memory artifact registry."""

    def __init__(self):
        self._artifacts: Dict[str, ArtifactRecord] = {}

    def register_artifact(self, artifact_type: str, case_id: str,
                          produced_by: str, data: Any) -> ArtifactRecord:
        artifact_id = f"{artifact_type}-{uuid.uuid4().hex[:8]}"
        record = ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            case_id=case_id,
            produced_by=produced_by,
            data=data,
        )
        self._artifacts[artifact_id] = record
        return record

    def get(self, artifact_id: str) -> Optional[ArtifactRecord]:
        return self._artifacts.get(artifact_id)

    def list_by_case(self, case_id: str) -> List[ArtifactRecord]:
        return [a for a in self._artifacts.values() if a.case_id == case_id]
