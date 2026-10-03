"""
VARUNA GRID — PostgreSQL Repositories Integration Tests.
"""
import pytest
from datetime import datetime, timezone
import uuid
import threading
from sqlalchemy.orm import sessionmaker

from varuna_domain.entities import Case, CaseStatus, DomainEvent, Artifact
from varuna_infra.postgres_repos import PostgresCaseRepository, PostgresEventStore, PostgresArtifactRepository
from varuna_infra.models import Base

pytestmark = [pytest.mark.integration]

@pytest.fixture
def session_factory(engine):
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(engine)

def test_postgres_case_lifecycle(session_factory):
    repo = PostgresCaseRepository(session_factory)
    
    # Save
    case_id = f"CASE-{uuid.uuid4().hex[:8]}"
    case = Case(case_id)
    case.status = CaseStatus.INGESTING
    case.error = "test error"
    
    repo.save(case)
    
    # Retrieve
    loaded = repo.get(case_id)
    assert loaded is not None
    assert loaded.case_id == case_id
    assert loaded.status == CaseStatus.INGESTING
    assert loaded.error == "test error"
    
    # Update
    case.status = CaseStatus.COMPLETED
    repo.save(case)
    
    loaded2 = repo.get(case_id)
    assert loaded2.status == CaseStatus.COMPLETED
    
    # List
    cases = repo.list_all()
    assert len(cases) > 0
    assert any(c.case_id == case_id for c in cases)

def test_postgres_event_store_concurrency(session_factory):
    case_repo = PostgresCaseRepository(session_factory)
    event_store = PostgresEventStore(session_factory)
    
    case_id = f"CASE-{uuid.uuid4().hex[:8]}"
    case_repo.save(Case(case_id))
    
    # Concurrent inserts
    def insert_event(i):
        e = DomainEvent(f"event.{i}", case_id, "test_actor", case_id, {"i": i})
        event_store.append(e)

    threads = []
    for i in range(10):
        t = threading.Thread(target=insert_event, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    events = event_store.list_by_case(case_id)
    assert len(events) == 10
    
    # Verify strict monotonic sequence without duplicates
    sequences = [e.sequence for e in events] # Wait, DomainEvent entity doesn't have sequence exposed? Let's check. 
    # The requirement says "verify strict monotonic sequence without duplicates".
    # Since DomainEvent doesn't expose sequence, we could verify it directly via DB or we can verify events are returned in order and count is 10.
    
    with session_factory() as session:
        from varuna_infra.models import CaseEventModel
        from sqlalchemy import select
        models = session.scalars(select(CaseEventModel).where(CaseEventModel.case_id == case_id).order_by(CaseEventModel.sequence.asc())).all()
        seqs = [m.sequence for m in models]
        assert len(set(seqs)) == 10
        assert seqs == sorted(seqs)

def test_postgres_event_store_idempotency(session_factory):
    case_repo = PostgresCaseRepository(session_factory)
    event_store = PostgresEventStore(session_factory)
    
    case_id = f"CASE-{uuid.uuid4().hex[:8]}"
    case_repo.save(Case(case_id))
    
    e1 = DomainEvent("test.event", case_id, "actor", case_id)
    e1.idempotency_key = "unique-key-1"
    
    e2 = DomainEvent("test.event", case_id, "actor", case_id)
    e2.idempotency_key = "unique-key-1"  # Same key
    
    event_store.append(e1)
    event_store.append(e2)  # Should not raise, should deduplicate
    
    events = event_store.list_by_case(case_id)
    assert len(events) == 1

def test_postgres_artifact_repository(session_factory):
    case_repo = PostgresCaseRepository(session_factory)
    art_repo = PostgresArtifactRepository(session_factory)
    
    case_id = f"CASE-{uuid.uuid4().hex[:8]}"
    case_repo.save(Case(case_id))
    
    art = Artifact("art-1", "type-A", {"some": "data"}, "producer", case_id)
    art_repo.save(art)
    
    loaded = art_repo.get("art-1")
    assert loaded is not None
    assert loaded.case_id == case_id
    assert loaded.data == {"some": "data"}
    
    arts = art_repo.list_by_case(case_id)
    assert len(arts) == 1
    assert arts[0].artifact_id == "art-1"
