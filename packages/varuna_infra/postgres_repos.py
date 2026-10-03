"""
VARUNA GRID — PostgreSQL Repositories.
"""
from typing import List, Optional
import json

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert

from varuna_domain.entities import Case, Artifact, DomainEvent, CaseStatus, ScientificStatus
from varuna_domain.ports import CaseRepository, ArtifactRepository, EventRepository
from varuna_infra.models import CaseModel, CaseEventModel, ArtifactModel

class PostgresCaseRepository(CaseRepository):
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def save(self, case: Case) -> None:
        with self.session_factory() as session:
            stmt = insert(CaseModel).values(
                case_id=case.case_id,
                status=case.status.value,
                created_at=case.created_at,
                updated_at=case.updated_at,
                error=case.error,
                metadata_json=case.metadata,
            ).on_conflict_do_update(
                index_elements=['case_id'],
                set_={
                    'status': case.status.value,
                    'updated_at': case.updated_at,
                    'error': case.error,
                    'metadata_json': case.metadata,
                }
            )
            session.execute(stmt)
            session.commit()

    def get(self, case_id: str) -> Optional[Case]:
        with self.session_factory() as session:
            model = session.scalar(select(CaseModel).where(CaseModel.case_id == case_id))
            if not model:
                return None
            case = Case(case_id=model.case_id)
            case.status = CaseStatus(model.status)
            case.created_at = model.created_at
            case.updated_at = model.updated_at
            case.error = model.error
            case.metadata = model.metadata_json or {}
            return case

    def list_all(self) -> List[Case]:
        with self.session_factory() as session:
            models = session.scalars(select(CaseModel).order_by(CaseModel.created_at.desc())).all()
            cases = []
            for m in models:
                c = Case(case_id=m.case_id)
                c.status = CaseStatus(m.status)
                c.created_at = m.created_at
                c.updated_at = m.updated_at
                c.error = m.error
                cases.append(c)
            return cases


class PostgresEventStore(EventRepository):
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def append(self, event: DomainEvent) -> None:
        with self.session_factory() as session:
            # Concurrency-safe sequence generation
            result = session.execute(
                text("UPDATE cases SET event_sequence_current = event_sequence_current + 1 WHERE case_id = :case_id RETURNING event_sequence_current"),
                {"case_id": event.case_id}
            )
            seq = result.scalar()
            if seq is None:
                raise ValueError(f"Case {event.case_id} not found when appending event.")

            stmt = insert(CaseEventModel).values(
                event_id=event.event_id,
                case_id=event.case_id,
                event_type=event.event_type,
                actor=event.actor,
                correlation_id=event.correlation_id,
                sequence=seq,
                payload=event.payload,
                timestamp=event.timestamp,
                idempotency_key=event.idempotency_key
            ).on_conflict_do_nothing(
                index_elements=['case_id', 'idempotency_key']
            )
            session.execute(stmt)
            session.commit()

    def list_all(self) -> List[DomainEvent]:
        with self.session_factory() as session:
            models = session.scalars(select(CaseEventModel).order_by(CaseEventModel.timestamp.desc())).all()
            return [self._to_entity(m) for m in models]

    def list_by_case(self, case_id: str) -> List[DomainEvent]:
        with self.session_factory() as session:
            models = session.scalars(select(CaseEventModel).where(CaseEventModel.case_id == case_id).order_by(CaseEventModel.sequence.asc())).all()
            return [self._to_entity(m) for m in models]

    def count(self) -> int:
        with self.session_factory() as session:
            count = session.scalar(text("SELECT COUNT(*) FROM case_events"))
            return count or 0

    def _to_entity(self, model: CaseEventModel) -> DomainEvent:
        e = DomainEvent(
            event_type=model.event_type,
            case_id=model.case_id,
            actor=model.actor,
            correlation_id=model.correlation_id,
            payload=model.payload
        )
        e.event_id = model.event_id
        e.timestamp = model.timestamp
        e.idempotency_key = model.idempotency_key
        return e


class PostgresArtifactRepository(ArtifactRepository):
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def save(self, artifact: Artifact) -> None:
        with self.session_factory() as session:
            stmt = insert(ArtifactModel).values(
                artifact_id=artifact.artifact_id,
                case_id=artifact.case_id,
                artifact_type=artifact.artifact_type,
                produced_by=artifact.produced_by,
                metadata_json=artifact.data if isinstance(artifact.data, dict) else {"data": "binary or custom format"},
                created_at=artifact.created_at,
                storage_key=artifact.storage_key,
                content_hash=artifact.content_hash,
            ).on_conflict_do_update(
                index_elements=['artifact_id'],
                set_={
                    'metadata_json': artifact.data if isinstance(artifact.data, dict) else {"data": "binary or custom format"},
                    'storage_key': artifact.storage_key,
                    'content_hash': artifact.content_hash,
                }
            )
            session.execute(stmt)
            session.commit()

    def get(self, artifact_id: str) -> Optional[Artifact]:
        with self.session_factory() as session:
            model = session.scalar(select(ArtifactModel).where(ArtifactModel.artifact_id == artifact_id))
            if not model:
                return None
            return self._to_entity(model)

    def list_by_case(self, case_id: str) -> List[Artifact]:
        with self.session_factory() as session:
            models = session.scalars(select(ArtifactModel).where(ArtifactModel.case_id == case_id).order_by(ArtifactModel.created_at.asc())).all()
            return [self._to_entity(m) for m in models]

    def _to_entity(self, model: ArtifactModel) -> Artifact:
        a = Artifact(
            artifact_id=model.artifact_id,
            artifact_type=model.artifact_type,
            data=model.metadata_json,
            produced_by=model.produced_by,
            case_id=model.case_id
        )
        a.created_at = model.created_at
        a.storage_key = model.storage_key
        a.content_hash = model.content_hash
        return a
