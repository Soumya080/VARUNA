"""
VARUNA GRID — API Dependencies (DI).
"""
from fastapi import Depends
from sqlalchemy.orm import sessionmaker

from apps.api.config import settings
from varuna_infra.database import create_session_factory
from varuna_domain.case_workflow import CaseWorkflow

# Keep singleton repositories/stores to avoid recreating them on every request
_session_factory = None
if settings.use_postgres:
    _session_factory = create_session_factory(settings.database_url)

_in_memory_case_repo = None
_in_memory_artifact_repo = None
_in_memory_event_store = None
_in_memory_object_store = None

def get_case_repo():
    global _in_memory_case_repo
    if settings.use_postgres:
        from varuna_infra.postgres_repos import PostgresCaseRepository
        return PostgresCaseRepository(_session_factory)
    else:
        if _in_memory_case_repo is None:
            from varuna_domain.repositories import InMemoryCaseRepository
            _in_memory_case_repo = InMemoryCaseRepository()
        return _in_memory_case_repo

def get_artifact_repo():
    global _in_memory_artifact_repo
    if settings.use_postgres:
        from varuna_infra.postgres_repos import PostgresArtifactRepository
        return PostgresArtifactRepository(_session_factory)
    else:
        if _in_memory_artifact_repo is None:
            from varuna_domain.repositories import InMemoryArtifactRepository
            _in_memory_artifact_repo = InMemoryArtifactRepository()
        return _in_memory_artifact_repo

def get_event_repo():
    global _in_memory_event_store
    if settings.use_postgres:
        from varuna_infra.postgres_repos import PostgresEventStore
        return PostgresEventStore(_session_factory)
    else:
        if _in_memory_event_store is None:
            from varuna_domain.repositories import InMemoryEventStore
            _in_memory_event_store = InMemoryEventStore()
        return _in_memory_event_store

def get_object_store():
    global _in_memory_object_store
    if settings.use_minio:
        from varuna_infra.minio_store import MinioObjectStore
        return MinioObjectStore(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket_name=settings.minio_bucket,
            secure=settings.minio_secure
        )
    else:
        if _in_memory_object_store is None:
            from varuna_infra.inmemory_store import InMemoryObjectStore
            _in_memory_object_store = InMemoryObjectStore()
        return _in_memory_object_store


def get_workflow(
    case_repo = Depends(get_case_repo),
    artifact_repo = Depends(get_artifact_repo),
    event_repo = Depends(get_event_repo),
    object_store = Depends(get_object_store)
) -> CaseWorkflow:
    return CaseWorkflow(
        case_repo=case_repo,
        artifact_repo=artifact_repo,
        event_repo=event_repo,
        object_store=object_store
    )

def get_adapter_registry():
    from varuna_source_adapters.service import AdapterRegistry
    return AdapterRegistry.create_mock()

def get_model_registry():
    from varuna_domain.model_registry import InMemoryModelRegistry
    return InMemoryModelRegistry()

_in_memory_mission_repo = None

def get_mission_service():
    global _in_memory_mission_repo
    from varuna_missions.service import MissionService
    if _in_memory_mission_repo is None:
        from varuna_missions.repository import InMemoryMissionRepository
        _in_memory_mission_repo = InMemoryMissionRepository()
    return MissionService(repo=_in_memory_mission_repo)

def get_prahari_service():
    from varuna_domain.prahari.service import PrahariService
    from varuna_domain.prahari.mock import MockPrahariProvider
    return PrahariService(provider=MockPrahariProvider(), netra_service=None, workflow=None)

def get_abhiyan_service():
    from varuna_abhiyan.service import AbhiyanService
    from varuna_abhiyan.mock import MockAbhiyanProvider
    return AbhiyanService(provider=MockAbhiyanProvider())

def get_smriti_service():
    from varuna_smriti.service import SmritiService
    from varuna_smriti.mock import MockSmritiProvider
    return SmritiService(provider=MockSmritiProvider())

def get_alert_service():
    from varuna_alerts.service import AlertService
    from varuna_alerts.channels.mock_sms import MockSmsChannel
    return AlertService(channels=[MockSmsChannel()])
