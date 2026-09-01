"""
VARUNA GRID — PRAMAN: Provenance + Artifact Manager.

In-memory implementation for local demo. No MinIO required.
"""
import hashlib
import json
import uuid
from typing import Optional, Any, List
from varuna_domain.entities import Artifact
from varuna_domain.ports import ArtifactRepository, ObjectStore


def canonical_hash(payload: Any) -> str:
    """
    sha256 over a canonical JSON rendering. `sort_keys` makes the digest
    independent of insertion order; `default=str` keeps datetimes and enums
    hashable rather than raising on the artifacts this system actually
    produces.
    """
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PramanService:
    """Artifact registry."""

    def __init__(self, artifact_repo: ArtifactRepository, object_store: Optional[ObjectStore] = None):
        self._repo = artifact_repo
        self._object_store = object_store

    def register_artifact(self, artifact_type: str, case_id: str,
                          produced_by: str, data: Any) -> Artifact:
        artifact_id = f"{artifact_type}-{uuid.uuid4().hex[:8]}"
        record = Artifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            case_id=case_id,
            produced_by=produced_by,
            data=data,
        )

        # Content-hash EVERY artifact, not only bytes. Previously only the
        # `isinstance(data, bytes)` branch set `content_hash`, and CaseWorkflow
        # registers dicts exclusively -- so in practice no artifact had ever
        # been hashed and EvidenceManifest integrity was unverifiable for the
        # payloads actually in use. Dicts are hashed over canonical JSON
        # (sorted keys, tight separators) so the digest is stable across
        # processes and re-serialisations rather than depending on dict order.
        if isinstance(data, bytes):
            record.content_hash = hashlib.sha256(data).hexdigest()
            if self._object_store:
                storage_key = f"{case_id}/{artifact_type}/{artifact_id}.bin"
                self._object_store.put(storage_key, data)
                record.storage_key = storage_key
                record.data = None  # Don't store huge binary blobs in DB metadata
        else:
            record.content_hash = canonical_hash(data)

        self._repo.save(record)
        return record

    def verify(self, artifact_id: str) -> bool:
        """
        Recompute an artifact's digest and compare. Returns False for an
        artifact whose payload no longer matches its recorded hash, and for
        one whose payload was offloaded to the object store (nothing local to
        check) -- callers must not read a False here as proof of tampering
        without also checking `storage_key`.
        """
        rec = self._repo.get(artifact_id)
        if rec is None or rec.content_hash is None or rec.data is None:
            return False
        actual = (hashlib.sha256(rec.data).hexdigest() if isinstance(rec.data, bytes)
                  else canonical_hash(rec.data))
        return actual == rec.content_hash

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._repo.get(artifact_id)

    def list_by_case(self, case_id: str) -> List[Artifact]:
        return self._repo.list_by_case(case_id)
