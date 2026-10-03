"""
Phase 1 — operational state must survive an API restart.

Before this, restarting the process erased every human decision in the
system (acknowledgements, escalations, mission approvals and their audit
trail) while the advisory SMRITI summary survived — exactly backwards for
an auditable product. These tests simulate a restart by constructing a
second store over the same file.
"""
from datetime import datetime, timezone

import pytest

from varuna_alerts.lifecycle import AlertLifecycleStatus, AlertRecord
from varuna_alerts.lifecycle_store import InMemoryAlertStore
from varuna_contracts.operator_case import AlertSeverity
from varuna_contracts.schemas import AssetTasking, BBox, GeoPoint, SearchBox
from varuna_contracts.states import MissionRecord, MissionState
from varuna_infra.authorization import AuditEntry, AuditLog
from varuna_infra.jsonl_store import AppendJsonlStore, KeyedJsonlStore
from varuna_missions.repository import InMemoryMissionRepository


def _alert(alert_id="ALT-1", case_id="C1", key="C1|detection.presence|x|run"):
    return AlertRecord(
        alert_id=alert_id, case_id=case_id, event_type="detection.created",
        severity=AlertSeverity.HIGH, reason="first detection",
        is_simulated=True, correlation_key=key, dedupe_key=key,
        material_dimension="detection.presence",
    )


# ------------------------------------------------------------------ alerts

def test_alerts_survive_a_restart(tmp_path):
    path = tmp_path / "alerts.jsonl"
    store = InMemoryAlertStore(path)
    a = _alert()
    a.status = AlertLifecycleStatus.ACKNOWLEDGED
    a.acknowledged_by = "officer"
    a.acknowledged_at = datetime.now(timezone.utc)
    store.save(a)

    reborn = InMemoryAlertStore(path)          # simulated restart
    got = reborn.get("ALT-1")
    assert got is not None
    assert got.status is AlertLifecycleStatus.ACKNOWLEDGED
    assert got.acknowledged_by == "officer"
    assert got.severity is AlertSeverity.HIGH


def test_correlation_index_is_rebuilt_after_restart(tmp_path):
    """Dedupe depends on this lookup; if the index is not rebuilt, a restart
    silently re-alerts everything."""
    path = tmp_path / "alerts.jsonl"
    InMemoryAlertStore(path).save(_alert())
    reborn = InMemoryAlertStore(path)
    hit = reborn.get_by_correlation_key("C1|detection.presence|x|run")
    assert hit is not None and hit.alert_id == "ALT-1"


def test_transitions_and_routing_survive(tmp_path):
    path = tmp_path / "alerts.jsonl"
    a = _alert()
    a.transitions = [{"from": "-", "to": "created", "actor": "mce",
                      "reason": "first detection", "at": "2026-01-01T00:00:00Z",
                      "detail": {}}]
    a.routing = {"dimension": "detection.presence", "severity": "high",
                 "recipients": [{"role": "duty_officer", "rbac_role": "duty_officer",
                                 "reason": "rule"}],
                 "matched_rule": "r", "reason": "why"}
    InMemoryAlertStore(path).save(a)

    got = InMemoryAlertStore(path).get("ALT-1")
    assert got.transitions and got.transitions[0]["actor"] == "mce"
    assert got.routing["recipients"][0]["role"] == "duty_officer"


def test_in_memory_mode_is_still_supported():
    store = InMemoryAlertStore()
    assert store.persisted is False
    store.save(_alert())
    assert store.get("ALT-1") is not None


# ----------------------------------------------------------------- missions

def _tasking():
    return AssetTasking(
        asset_type="dornier", base_name="Base",
        search_box=SearchBox(bbox=BBox(min_lon=0, min_lat=0, max_lon=1, max_lat=1),
                             center=GeoPoint(lon=0.5, lat=0.5),
                             area_km2=1.0, phi_mass_contained=1.0),
        pattern="expanding_square", launch_time="2026-01-01T00:00:00Z",
        flight_hours=1.0, probability_of_detection=0.5, rationale="t")


def test_mission_approval_survives_a_restart(tmp_path):
    """The single most important thing to persist: a human authorising a
    physical asset dispatch."""
    path = tmp_path / "missions.jsonl"
    repo = InMemoryMissionRepository(path)
    m = MissionRecord(mission_id="MSN-1", case_id="C1", asset_id="A1",
                      state=MissionState.AVAILABLE)
    m.transition(MissionState.RESERVED)
    m.human_approved_by = "officer"
    m.transition(MissionState.ASSIGNED)
    repo.save(m)

    reborn = InMemoryMissionRepository(path)
    got = reborn.get("MSN-1")
    assert got is not None
    assert got.state is MissionState.ASSIGNED
    assert got.human_approved_by == "officer"
    assert reborn.list_by_case("C1") != []


def test_terminal_missions_are_excluded_from_active_but_kept_in_all(tmp_path):
    path = tmp_path / "missions.jsonl"
    repo = InMemoryMissionRepository(path)
    m = MissionRecord(mission_id="MSN-2", case_id="C1", asset_id="A1",
                      state=MissionState.COMPLETE)
    repo.save(m)
    reborn = InMemoryMissionRepository(path)
    assert reborn.list_active() == []
    assert len(reborn.all()) == 1, "mission history must not be lost"


# -------------------------------------------------------------------- audit

def test_audit_trail_survives_a_restart_and_keeps_order(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    for i, allowed in enumerate([False, True]):
        log.record(AuditEntry(principal_id=f"p{i}", role="duty_officer",
                              permission="approve_mission",
                              operation="mission.approve_and_assign",
                              allowed=allowed, subject_id="MSN-1"))

    reborn = AuditLog(path)
    entries = reborn.for_subject("MSN-1")
    assert len(entries) == 2
    assert [e.allowed for e in entries] == [False, True], "order must be preserved"
    assert len(reborn.denials()) == 1


def test_audit_appends_rather_than_rewriting(tmp_path):
    """A wholesale rewrite risks losing earlier decisions on a mid-write
    crash; the audit store must append."""
    path = tmp_path / "audit.jsonl"
    AuditLog(path).record(AuditEntry(principal_id="a", role="r", permission="p",
                                     operation="o", allowed=True))
    AuditLog(path).record(AuditEntry(principal_id="b", role="r", permission="p",
                                     operation="o", allowed=True))
    assert len(AuditLog(path).all()) == 2


# ----------------------------------------------------------- generic store

def test_corrupt_line_is_counted_not_fatal(tmp_path):
    """Losing one malformed record must not cost every acknowledgement."""
    path = tmp_path / "alerts.jsonl"
    InMemoryAlertStore(path).save(_alert())
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not valid json\n")

    reborn = InMemoryAlertStore(path)
    assert reborn.get("ALT-1") is not None, "good records must still load"
    assert reborn.load_errors == 1, "damage must be counted, not hidden"


def test_keyed_store_is_last_write_wins(tmp_path):
    path = tmp_path / "k.jsonl"
    s = KeyedJsonlStore(path, key=lambda d: d["id"],
                        loads=__import__("json").loads,
                        dumps=lambda d: __import__("json").dumps(d))
    s.put({"id": "x", "v": 1})
    s.put({"id": "x", "v": 2})
    reborn = KeyedJsonlStore(path, key=lambda d: d["id"],
                             loads=__import__("json").loads,
                             dumps=lambda d: __import__("json").dumps(d))
    assert len(reborn) == 1
    assert reborn.get("x")["v"] == 2


def test_append_store_preserves_duplicates_and_order(tmp_path):
    path = tmp_path / "a.jsonl"
    s = AppendJsonlStore(path, loads=__import__("json").loads,
                         dumps=lambda d: __import__("json").dumps(d))
    s.append({"n": 1}); s.append({"n": 1}); s.append({"n": 2})
    reborn = AppendJsonlStore(path, loads=__import__("json").loads,
                              dumps=lambda d: __import__("json").dumps(d))
    assert [r["n"] for r in reborn.all()] == [1, 1, 2]
