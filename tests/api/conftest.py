"""
Shared fixtures for tests/api. The alert-lifecycle and mission-service
singletons in apps.api.dependencies are intentionally process-lifetime
(fixing STEP 6's mission-audit-discard bug required exactly that
persistence). That is correct production behavior but makes them leak
state across test functions/modules within one pytest session — reset
them before and after every test in this directory so one test's
mutation of the shared CASE-VALID replay alert (or a live mission) can
never affect another test's assertions about a specific alert's or
mission's starting state.
"""
import pytest

import apps.api.dependencies as deps
import apps.api.routers.replay as replay_router


@pytest.fixture(autouse=True, scope="session")
def _isolate_persisted_state(tmp_path_factory):
    """Point persisted operational state at a throwaway directory.

    Phase 1 made alerts/missions/audit disk-backed under `reports/state`.
    Without this, the suite would read and mutate the SAME files the running
    API uses — so whatever a developer had clicked in the cockpit would leak
    into test expectations (and vice versa). Observed for real: a stray
    `mission.assigned` alert from a manual run broke two unrelated tests.
    """
    import os

    d = tmp_path_factory.mktemp("varuna_state")
    old = os.environ.get("VARUNA_STATE_DIR")
    os.environ["VARUNA_STATE_DIR"] = str(d)
    yield
    if old is None:
        os.environ.pop("VARUNA_STATE_DIR", None)
    else:
        os.environ["VARUNA_STATE_DIR"] = old


@pytest.fixture(autouse=True)
def _isolated_alert_and_mission_singletons():
    def _reset():
        deps._alert_lifecycle_singleton = None
        deps._mission_service_singleton = None
        deps._in_memory_mission_repo = None
        deps._mission_audit_log = None
        # The replay endpoint's composed-response cache is a process-lifetime
        # singleton in the same family. It must be reset here too: a cached
        # response skips run_replay_case(), and that call is what syncs the
        # run's alerts into the (just-reset) alert store — so leaving the
        # cache warm across tests would hand a test an empty alert store.
        replay_router._COMPOSED_CACHE.clear()
        # Workstream A singletons. The snapshot store is what the Material
        # Change Engine diffs against: leaving it warm makes a re-run look
        # like "nothing changed", so a later test would see zero alerts.
        deps._alert_store_singleton = None
        deps._alert_orchestrator_singleton = None
        deps._snapshot_store_singleton = None

    _reset()
    yield
    _reset()
