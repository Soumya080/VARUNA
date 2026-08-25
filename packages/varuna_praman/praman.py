"""
VARUNA GRID — PRAMAN: Provenance + Artifact Manager.

In-memory implementation for local demo. No MinIO required.
"""
import uuid
from typing import Optional, Any, List
from varuna_domain.entities import Artifact
from varuna_domain.ports import ArtifactRepository, ObjectStore


class PramanService:
    """Artifact registry."""

    def __init__(self, artifact_repo: ArtifactRepository, object_store: Optional[ObjectStore] = None):
        self._repo = artifact_repo
        self._object_store = object_store

    def register_artifact(self, artifact_type: str, case_id: str,
                          produced_by: str, data: Any) -> Artifact:
        import hashlib
        artifact_id = f"{artifact_type}-{uuid.uuid4().hex[:8]}"
        record = Artifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            case_id=case_id,
            produced_by=produced_by,
            data=data,
        )

        # If it's raw bytes or non-dict and we have an object store, upload it
        if self._object_store and isinstance(data, bytes):
            storage_key = f"{case_id}/{artifact_type}/{artifact_id}.bin"
            self._object_store.put(storage_key, data)
            record.storage_key = storage_key
            record.content_hash = hashlib.sha256(data).hexdigest()
            record.data = None # Don't store huge binary blobs in DB metadata

        self._repo.save(record)
        return record

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._repo.get(artifact_id)

    def list_by_case(self, case_id: str) -> List[Artifact]:
        return self._repo.list_by_case(case_id)
