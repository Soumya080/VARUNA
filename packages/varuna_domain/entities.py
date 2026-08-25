"""
VARUNA GRID — Domain entities for case management.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from enum import Enum


class CaseStatus(str, Enum):
    CREATED = "created"
    INGESTING = "ingesting"
    GUARDING = "guarding"
    RECONSTRUCTING = "reconstructing"
    ATTRIBUTING = "attributing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class ScientificStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"


class Artifact:
    def __init__(self, artifact_id: str, artifact_type: str, data: Any,
                 produced_by: str, case_id: str):
        self.artifact_id = artifact_id
        self.artifact_type = artifact_type
        self.data = data
        self.produced_by = produced_by
        self.case_id = case_id
        self.created_at = datetime.now(timezone.utc)


class DomainEvent:
    def __init__(self, event_type: str, case_id: str, actor: str,
                 correlation_id: str, payload: Optional[Dict] = None):
        self.event_type = event_type
        self.case_id = case_id
        self.actor = actor
        self.correlation_id = correlation_id
        self.payload = payload or {}
        self.timestamp = datetime.now(timezone.utc)
        self.idempotency_key = f"{event_type}:{case_id}:{self.timestamp.isoformat()}"


class Case:
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.status = CaseStatus.CREATED
        self.scientific_status = ScientificStatus.EXPERIMENTAL
        self.artifacts: Dict[str, Artifact] = {}
        self.events: List[DomainEvent] = []
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.error: Optional[str] = None

    def add_artifact(self, artifact: Artifact):
        self.artifacts[artifact.artifact_id] = artifact
        self.updated_at = datetime.now(timezone.utc)

    def emit_event(self, event_type: str, actor: str, payload: Optional[Dict] = None):
        event = DomainEvent(
            event_type=event_type,
            case_id=self.case_id,
            actor=actor,
            correlation_id=self.case_id,
            payload=payload,
        )
        self.events.append(event)
        self.updated_at = datetime.now(timezone.utc)
        return event

    def transition(self, new_status: CaseStatus, actor: str = "system"):
        old = self.status
        self.status = new_status
        self.emit_event(
            f"case.status.{new_status.value}",
            actor=actor,
            payload={"from": old.value, "to": new_status.value},
        )
