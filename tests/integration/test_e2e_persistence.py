"""
VARUNA GRID — Persistent Local Demo (M3.5).
End-to-End integration test.
"""
import pytest
import time
import os
import uuid
from sqlalchemy.orm import sessionmaker

from tests.fixtures.case_0001 import generate_case_0001
from varuna_domain.case_workflow import CaseWorkflow
from varuna_infra.postgres_repos import PostgresCaseRepository, PostgresArtifactRepository, PostgresEventStore
from varuna_infra.minio_store import MinioObjectStore
from varuna_domain.entities import CaseStatus
from apps.api.config import settings
from varuna_infra.models import Base

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

@pytest.fixture
def session_factory(engine):
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(engine)

@pytest.fixture
def object_store():
    # Only run if minio is available via settings or mock it
    if not settings.use_minio:
        pytest.skip("MinIO not configured for test")
    
    return MinioObjectStore(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket_name=settings.minio_bucket,
        secure=settings.minio_secure,
    )

def test_e2e_persistence(session_factory, object_store):
    fixture = generate_case_0001()
    case_id = f"M35-E2E-{uuid.uuid4().hex[:8]}"
    
    # Run workflow within a session
    with session_factory() as session:
        cases = PostgresCaseRepository(lambda: session)
        artifacts = PostgresArtifactRepository(lambda: session)
        events = PostgresEventStore(lambda: session)
        
        workflow = CaseWorkflow(cases, artifacts, events, object_store)
        
        result = workflow.run_full(
            case_id=case_id,
            slick_lons=fixture["slick_lons"],
            slick_lats=fixture["slick_lats"],
            tracks=fixture["tracks"],
            obs_time_hours=fixture["obs_time_hours"],
            seed=fixture["seed"],
            latent_prior=fixture["config"]["latent_prior"],
            age_prior_mean=fixture["config"]["age_prior_mean"],
            age_prior_std=fixture["config"]["age_prior_std"],
        )
        
        session.commit()
    
    assert result['status'] == "completed"
    
    # Phase 2: Simulate restart by using a new session
    with session_factory() as session:
        cases = PostgresCaseRepository(lambda: session)
        artifacts = PostgresArtifactRepository(lambda: session)
        events = PostgresEventStore(lambda: session)
        
        # 1. Retrieve case
        case = cases.get(case_id)
        assert case is not None
        assert case.status == CaseStatus.COMPLETED
        
        # 2. Retrieve events
        case_events = events.list_by_case(case_id)
        assert len(case_events) >= 6
        
        # 3. Verify monotonic sequence
        seqs = [e.sequence for e in case_events]
        assert len(set(seqs)) == len(seqs)
        assert seqs == sorted(seqs)
        
        # 4. Retrieve artifacts
        case_artifacts = artifacts.list_by_case(case_id)
        assert len(case_artifacts) >= 4
        
        # 5. Verify object store accessibility
        has_blobs = 0
        for art in case_artifacts:
            if art.storage_key:
                has_blobs += 1
                exists = object_store._client.stat_object(object_store.bucket, art.storage_key)
                assert exists

        assert has_blobs > 0
