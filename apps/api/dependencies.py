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
_mission_audit_log = None
_mission_service_singleton = None

def get_mission_service():
    """STEP 6 fix (docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md, item 12):
    this previously constructed a *new* `MissionService` per call, and
    `MissionService.__init__` defaults to a fresh, empty `AuditLog()` when
    none is passed — so every authorization decision `approve_and_assign()`
    recorded was discarded before any caller could ever read it back. Now a
    single `AuditLog` (and the same `MissionService` instance) is reused
    for the process lifetime, matching the singleton pattern
    `get_golden_case_workflow()` already uses for its repos."""
    global _in_memory_mission_repo, _mission_audit_log, _mission_service_singleton
    from varuna_missions.service import MissionService
    if _mission_service_singleton is None:
        from varuna_infra.authorization import AuditLog
        from varuna_missions.repository import InMemoryMissionRepository
        _in_memory_mission_repo = InMemoryMissionRepository()
        _mission_audit_log = AuditLog()
        _mission_service_singleton = MissionService(
            repo=_in_memory_mission_repo, audit=_mission_audit_log,
            alert_service=get_alert_service(),
            alert_lifecycle=get_alert_lifecycle_service())
    return _mission_service_singleton

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

_alert_lifecycle_singleton = None
_alert_orchestrator_singleton = None
_snapshot_store_singleton = None
_alert_store_singleton = None


def get_alert_store():
    """The ONE alert store (Workstream A: no second store)."""
    global _alert_store_singleton
    if _alert_store_singleton is None:
        from varuna_alerts.lifecycle_store import InMemoryAlertStore
        _alert_store_singleton = InMemoryAlertStore()
    return _alert_store_singleton


def get_alert_orchestrator():
    """Material change -> dedupe -> enrich -> prioritise -> route -> deliver."""
    global _alert_orchestrator_singleton
    if _alert_orchestrator_singleton is None:
        from varuna_alerts.channel_orchestrator import ChannelOrchestrator
        from varuna_alerts.orchestrator import AlertOrchestrator
        _alert_orchestrator_singleton = AlertOrchestrator(
            get_alert_store(), channels=ChannelOrchestrator())
    return _alert_orchestrator_singleton


def get_case_snapshot_store():
    global _snapshot_store_singleton
    if _snapshot_store_singleton is None:
        from varuna_integration.operational_loop import CaseSnapshotStore
        _snapshot_store_singleton = CaseSnapshotStore()
    return _snapshot_store_singleton

def get_alert_lifecycle_service():
    """STEP 6: singleton, same reasoning as `get_mission_service()` above —
    an alert acknowledged in one request must still show acknowledged in
    the next, so this cannot be constructed fresh per call."""
    global _alert_lifecycle_singleton
    if _alert_lifecycle_singleton is None:
        from varuna_alerts.lifecycle_service import AlertLifecycleService
        _alert_lifecycle_singleton = AlertLifecycleService(get_alert_store())
    return _alert_lifecycle_singleton

# --------------------------------------------------------------------------
# STEP 4 (frontend integration track): the ONLY place `GoldenCaseWorkflow`
# is constructed for API serving. Distinct from `get_workflow()` above
# (legacy `CaseWorkflow`, unchanged, still backs every existing case route
# per docs/product/CANONICAL_WORKFLOW_POLICY.md). This exists to serve
# `apps/api/routers/replay.py`'s read-only replay-case endpoint, added in
# this task because no existing route could produce a GoldenCaseWorkflow-
# sourced (and therefore intelligence-composable) OperatorCase — see
# docs/architecture/ADR-0014-frontend-replay-endpoint.md.
# --------------------------------------------------------------------------
_golden_case_repo = None
_golden_artifact_repo = None
_golden_event_store = None
_golden_smriti_store = None

def get_golden_case_workflow():
    global _golden_case_repo, _golden_artifact_repo, _golden_event_store
    from varuna_domain.golden_case_engine import GoldenCaseWorkflow
    from varuna_domain.repositories import (
        InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
    )
    if _golden_case_repo is None:
        _golden_case_repo = InMemoryCaseRepository()
        _golden_artifact_repo = InMemoryArtifactRepository()
        _golden_event_store = InMemoryEventStore()
    return GoldenCaseWorkflow(
        _golden_case_repo, _golden_artifact_repo, _golden_event_store,
        object_store=get_object_store(),
        mission_service=get_mission_service(),
        # Workstream A: the legacy delivery-receipt correlation
        # (_sync_alerts_to_lifecycle) is deliberately NOT wired here any
        # more. The Alert Orchestrator is now the single alert producer —
        # wiring both would give one case two parallel alert systems.
        alert_service=get_alert_service(),
    )

def get_replay_smriti_store():
    global _golden_smriti_store
    if _golden_smriti_store is None:
        from pathlib import Path
        from varuna_smriti.memory import SmritiStore
        path = Path(__file__).resolve().parents[2] / "reports" / "demo" / "api_replay_smriti_memory.jsonl"
        _golden_smriti_store = SmritiStore(path)
    return _golden_smriti_store
