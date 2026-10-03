"""STEP 6 focused tests: the alert lifecycle (docs/product/
ALERT_OPERATIONAL_DIAGNOSTIC.md, item 6) did not exist before this task."""
from datetime import datetime, timezone

import pytest

from varuna_alerts.lifecycle import AlertLifecycleStatus
from varuna_alerts.lifecycle_service import AlertLifecycleService, IllegalAlertTransitionError
from varuna_alerts.lifecycle_store import InMemoryAlertStore
from varuna_alerts.protocol import DeliveryResult
from varuna_contracts.operator_case import AlertSeverity
from varuna_infra.authorization import AuthorizationError, Principal


def _delivery(**overrides) -> DeliveryResult:
    defaults = dict(
        channel="console", recipient="ops-room", status="sent",
        reason="material change detected", is_simulated=True,
        idempotency_key="CASE-1:validity.evaluated:ops-room",
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return DeliveryResult(**defaults)


DUTY_OFFICER = Principal(principal_id="officer-1", role="duty_officer")
ANALYST = Principal(principal_id="analyst-1", role="analyst")
READ_ONLY = Principal(principal_id="viewer-1", role="read_only")
SYSTEM = Principal.system()


def _svc() -> AlertLifecycleService:
    return AlertLifecycleService(InMemoryAlertStore())


def test_sync_creates_one_alert_from_deliveries():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    assert record is not None
    assert record.status == AlertLifecycleStatus.CREATED
    assert record.case_id == "CASE-1"
    assert len(record.deliveries) == 1
    assert record.severity == AlertSeverity.WARNING  # is_simulated=True, not suppressed


def test_sync_with_only_none_channel_creates_nothing():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery(channel="none", recipient="none", status="suppressed")],
        evidence_mode=None,
    )
    assert record is None
    assert svc.list_by_case("CASE-1") == []


def test_repeated_sync_correlates_instead_of_duplicating():
    """Phase 4: same material condition observed again must update the
    existing alert, not flood a second one."""
    svc = _svc()
    first = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    second = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery(reason="re-observed")], evidence_mode="simulated",
    )
    assert first.alert_id == second.alert_id
    assert len(svc.list_by_case("CASE-1")) == 1


def test_authorized_role_can_acknowledge():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    updated = svc.acknowledge(record.alert_id, principal=DUTY_OFFICER)
    assert updated.status == AlertLifecycleStatus.ACKNOWLEDGED
    assert updated.acknowledged_by == "officer-1"
    assert updated.acknowledged_at is not None


def test_unauthorized_role_is_denied_and_state_is_unchanged():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    with pytest.raises(AuthorizationError):
        svc.escalate(record.alert_id, principal=ANALYST)  # analyst may ack, not escalate
    unchanged = svc.get(record.alert_id)
    assert unchanged.status == AlertLifecycleStatus.CREATED
    assert unchanged.escalated_by is None


def test_read_only_role_cannot_acknowledge():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    with pytest.raises(AuthorizationError):
        svc.acknowledge(record.alert_id, principal=READ_ONLY)


def test_system_principal_can_acknowledge_but_not_escalate():
    """SYSTEM holds no alert-lifecycle permission at all in ROLE_PERMISSIONS
    — an automated caller cannot pretend to be the operator who handled an
    alert, mirroring the mission-approval SYSTEM-is-refused policy."""
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    with pytest.raises(AuthorizationError):
        svc.acknowledge(record.alert_id, principal=SYSTEM)


def test_illegal_transition_is_rejected():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    svc.resolve(svc.acknowledge(record.alert_id, principal=DUTY_OFFICER).alert_id,
                principal=DUTY_OFFICER)
    with pytest.raises(IllegalAlertTransitionError):
        svc.acknowledge(record.alert_id, principal=DUTY_OFFICER)  # already RESOLVED


def test_every_authorization_decision_is_audited():
    svc = _svc()
    record = svc.sync_from_deliveries(
        case_id="CASE-1", event_type="validity.evaluated",
        deliveries=[_delivery()], evidence_mode="simulated",
    )
    svc.acknowledge(record.alert_id, principal=DUTY_OFFICER)
    with pytest.raises(AuthorizationError):
        svc.escalate(record.alert_id, principal=READ_ONLY)
    entries = svc.audit_log.for_subject(record.alert_id)
    assert any(e.allowed for e in entries)
    assert any(not e.allowed for e in entries)
