"""
VARUNA GRID — Domain entities for case management.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from enum import Enum


class CaseStatus(str, Enum):
    # Original CaseWorkflow (v1) lifecycle -- kept verbatim, unchanged, so every
    # existing caller/test that compares against these values keeps working.
    CREATED = "created"
    INGESTING = "ingesting"
    GUARDING = "guarding"
    RECONSTRUCTING = "reconstructing"
    ATTRIBUTING = "attributing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    QUARANTINED = "quarantined"

    # Golden Case Engine lifecycle (packages/varuna_domain/golden_case_engine.py) --
    # the full Observation->Alerts chain the v1 lifecycle above never modeled.
    # Additive only: nothing above was renamed or removed. CASE_CREATED and
    # COMPLETED->COMPLETE are two names for "the same idea at two different
    # levels of granularity", not a conflict -- the golden engine picks one
    # vocabulary and uses it consistently for its own transitions.
    CASE_CREATED = "case_created"
    INGESTED = "ingested"
    DETECTING = "detecting"
    VALIDATING = "validating"
    FORECASTING = "forecasting"
    DECIDING = "deciding"
    MISSION = "mission"
    ALERTING = "alerting"
    COMPLETE = "complete"
    # Operational/scientific outcomes distinct from FAILED (a genuine break):
    # BLOCKED = a stage ran and a precondition stopped the case (fail-closed,
    # not broken); UNAVAILABLE = a producer could not run at all (no data, no
    # checkpoint); OOD = the model ran and reported input outside its trained
    # distribution (a specific, honest UNAVAILABLE variant worth naming).
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    OOD = "ood"


class ScientificStatus(str, Enum):
    EXPERIMENTAL = "experimental"
    UNVALIDATED = "unvalidated"


class Artifact:
    def __init__(self, artifact_id: str, artifact_type: str, data: Any,
                 produced_by: str, case_id: str):
        self.artifact_id = artifact_id
        self.artifact_type = artifact_type
        self.data = data
        self.produced_by = produced_by
        self.case_id = case_id
        self.storage_key: Optional[str] = None
        self.content_hash: Optional[str] = None
        self.created_at = datetime.now(timezone.utc)


class DomainEvent:
    def __init__(self, event_type: str, case_id: str, actor: str,
                 correlation_id: str, payload: Optional[Dict] = None):
        import uuid
        self.event_id = uuid.uuid4().hex[:12]
        self.event_type = event_type
        self.case_id = case_id
        self.actor = actor
        self.correlation_id = correlation_id
        self.payload = payload or {}
        self.timestamp = datetime.now(timezone.utc)
        self.idempotency_key = f"{event_type}:{case_id}:{self.event_id}"
        self.sequence: Optional[int] = None


class Case:
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.status = CaseStatus.CREATED
        self.scientific_status = ScientificStatus.EXPERIMENTAL
        self.artifacts: Dict[str, Artifact] = {}
        self.events: List[DomainEvent] = []
        self.metadata: Dict[str, Any] = {}
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
