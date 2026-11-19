"""
Workstream A — operational platform tests.

Covers the Material Change Engine, severity, dedupe, role routing, channel
honesty, and the extended alert lifecycle.
"""
import pytest

from varuna_alerts.channel_orchestrator import (
    ChannelMode, ChannelOrchestrator, DeliveryStatus,
)
from varuna_alerts.lifecycle import AlertLifecycleStatus, is_legal_alert_transition
from varuna_alerts.lifecycle_store import InMemoryAlertStore
from varuna_alerts.material_change import (
    CONFIDENCE_DELTA, MaterialDimension, ORIGIN_MOVE_KM, evaluate_material_changes,
)
from varuna_alerts.orchestrator import AlertOrchestrator, dedupe_identity
from varuna_alerts.routing_policy import OperationalRole, route
from varuna_contracts.operator_case import AlertSeverity


# --------------------------------------------------------------- fixtures

def _case(*, case_id="C1", detection_conf=0.7, validity="valid",
          landfalls=1, lon=-88.97, lat=28.936, engine_mode="replay"):
    """A dict shaped like the parts of OperatorCase the engine reads.
    Using dicts deliberately: the engine must work on both pydantic objects
    and the plain dicts the projection layer passes around."""
    return {
        "case_id": case_id,
        "system_status": {"engine_mode": engine_mode},
        "detection": {
            "status": "produced", "evidence_mode": "real",
            "value": {"slick_id": "s1", "confidence": detection_conf},
        },
        "starting_point": {
            "status": "STARTING_POINT_AVAILABLE", "evidence_mode": "real",
            "point": {"lon": lon, "lat": lat},
        },
        "attribution": {"status": "produced", "evidence_mode": "real",
                        "value": {"top_posterior": 0.7}},
        "validity": {"status": "produced", "evidence_mode": "real",
                     "value": {"state": validity}},
        "forecast": {
            "status": "produced", "evidence_mode": "real",
            "value": {"forecast_id": "f1",
                      "landfalls": [{"location_name": "Coast"}] * landfalls},
        },
        "mission": {"status": "produced", "evidence_mode": "real",
                    "value": [{"mission_id": "M1", "state": "available"}]},
    }


def _empty_case(case_id="C-OOD"):
    """A fail-closed case: nothing produced."""
    return {
        "case_id": case_id,
        "system_status": {"engine_mode": "replay"},
        "detection": {"status": "not_yet_produced", "value": None},
        "starting_point": {"status": "STARTING_POINT_UNAVAILABLE", "point": None},
        "attribution": {"status": "not_yet_produced", "value": None},
        "validity": {"status": "not_yet_produced", "value": None},
        "forecast": {"status": "not_yet_produced", "value": None},
        "mission": {"status": "not_yet_produced", "value": None},
    }


# ------------------------------------------------- material change engine

def test_first_sighting_reports_detection_and_landfall():
    changes = evaluate_material_changes(_case(), None)
    dims = {c.dimension for c in changes}
    assert MaterialDimension.DETECTION_PRESENCE in dims
    assert MaterialDimension.LANDFALL_PREDICTION in dims
    assert MaterialDimension.VALIDITY_STATE in dims


def test_identical_refresh_produces_no_material_change():
    """The core anti-spam property: re-seeing the same state is not news."""
    c = _case()
    assert evaluate_material_changes(c, c) == []


def test_fail_closed_case_produces_no_material_change():
    assert evaluate_material_changes(_empty_case(), None) == []


def test_confidence_change_below_threshold_is_not_material():
    prev = _case(detection_conf=0.70)
    cur = _case(detection_conf=0.70 + CONFIDENCE_DELTA / 2)
    dims = {c.dimension for c in evaluate_material_changes(cur, prev)}
    assert MaterialDimension.DETECTION_CONFIDENCE not in dims


def test_confidence_change_above_threshold_is_material():
    prev = _case(detection_conf=0.50)
    cur = _case(detection_conf=0.50 + CONFIDENCE_DELTA + 0.01)
    changes = [c for c in evaluate_material_changes(cur, prev)
               if c.dimension is MaterialDimension.DETECTION_CONFIDENCE]
    assert len(changes) == 1
    assert changes[0].previous == pytest.approx(0.50)
    assert changes[0].severity_basis  # must always be explainable


def test_small_origin_move_is_not_material_large_one_is():
    prev = _case()
    near = _case(lat=28.936 + 0.005)          # ~0.5 km
    far = _case(lat=28.936 + 0.20)            # ~22 km
    assert not any(c.dimension is MaterialDimension.ORIGIN_POSITION
                   for c in evaluate_material_changes(near, prev))
    moved = [c for c in evaluate_material_changes(far, prev)
             if c.dimension is MaterialDimension.ORIGIN_POSITION]
    assert len(moved) == 1
    assert f"{ORIGIN_MOVE_KM}" in moved[0].reason


def test_every_change_carries_previous_new_reason_and_evidence():
    for c in evaluate_material_changes(_case(), None):
        assert c.reason
        assert c.severity_basis
        assert c.dimension is not None
        assert c.case_id == "C1"


# ------------------------------------------------------------- severity

def test_landfall_while_action_blocked_is_critical():
    changes = evaluate_material_changes(_case(validity="restricted"), None)
    lf = [c for c in changes if c.dimension is MaterialDimension.LANDFALL_PREDICTION]
    assert lf and lf[0].severity is AlertSeverity.CRITICAL
    assert "blocks operational action" in lf[0].severity_basis


def test_landfall_while_action_allowed_is_high_not_critical():
    lf = [c for c in evaluate_material_changes(_case(validity="valid"), None)
          if c.dimension is MaterialDimension.LANDFALL_PREDICTION]
    assert lf and lf[0].severity is AlertSeverity.HIGH


def test_validity_degradation_is_high():
    prev = _case(validity="valid")
    cur = _case(validity="restricted")
    v = [c for c in evaluate_material_changes(cur, prev)
         if c.dimension is MaterialDimension.VALIDITY_STATE]
    assert v and v[0].severity is AlertSeverity.HIGH


# -------------------------------------------------------------- routing

def test_landfall_routes_to_environmental_and_shipping_authorities():
    d = route(MaterialDimension.LANDFALL_PREDICTION, AlertSeverity.HIGH)
    roles = {r.role for r in d.recipients}
    assert OperationalRole.STATE_PCB in roles
    assert OperationalRole.DG_SHIPPING in roles
    assert d.reason


def test_routing_is_not_notify_everyone():
    d = route(MaterialDimension.DETECTION_PRESENCE, AlertSeverity.HIGH)
    roles = {r.role for r in d.recipients}
    assert roles == {OperationalRole.DUTY_OFFICER}


def test_critical_always_reaches_supervisor():
    d = route(MaterialDimension.DETECTION_PRESENCE, AlertSeverity.CRITICAL)
    assert OperationalRole.SUPERVISOR in {r.role for r in d.recipients}


def test_external_stakeholders_hold_no_rbac_permissions():
    d = route(MaterialDimension.LANDFALL_PREDICTION, AlertSeverity.HIGH)
    for r in d.recipients:
        if r.role in (OperationalRole.STATE_PCB, OperationalRole.DG_SHIPPING,
                      OperationalRole.ENFORCEMENT):
            assert r.rbac_role is None, "external stakeholder must not map to an RBAC role"


# --------------------------------------------------------------- dedupe

def test_dedupe_identity_is_stable_and_dimension_scoped():
    changes = evaluate_material_changes(_case(), None)
    a = changes[0]
    assert dedupe_identity(a) == dedupe_identity(a)
    assert a.dimension.value in dedupe_identity(a)
    assert a.reason not in dedupe_identity(a), "dedupe must not key on alert text"


def test_orchestrator_dedupes_repeated_identical_change():
    store = InMemoryAlertStore()
    orch = AlertOrchestrator(store)
    change = evaluate_material_changes(_case(), None)[0]
    first = orch.process(change)
    second = orch.process(change)
    assert first.alert_id == second.alert_id
    assert len(store.list_by_case("C1")) == 1


def test_different_dimensions_create_different_alerts():
    store = InMemoryAlertStore()
    orch = AlertOrchestrator(store)
    orch.process_all(evaluate_material_changes(_case(), None))
    dims = {a.material_dimension for a in store.list_by_case("C1")}
    assert len(dims) >= 3


# ------------------------------------------------------- channel honesty

def test_unconfigured_channels_report_not_configured_never_success(monkeypatch):
    monkeypatch.delenv("VARUNA_SMTP_HOST", raising=False)
    monkeypatch.delenv("VARUNA_SMS_PROVIDER", raising=False)
    deliveries = ChannelOrchestrator().deliver(
        alert_id="a1", recipient_roles=["duty_officer"], subject="s", body="b")
    by_channel = {d.channel: d for d in deliveries}
    assert by_channel["email"].status is DeliveryStatus.NOT_CONFIGURED
    assert by_channel["email"].mode is ChannelMode.NOT_CONFIGURED
    assert by_channel["sms"].status is DeliveryStatus.NOT_CONFIGURED
    for d in deliveries:
        if d.mode is ChannelMode.NOT_CONFIGURED:
            assert d.status is not DeliveryStatus.DELIVERED


def test_dashboard_is_real_and_browser_push_is_honestly_simulated():
    deliveries = ChannelOrchestrator().deliver(
        alert_id="a1", recipient_roles=["duty_officer"], subject="s", body="b")
    by_channel = {d.channel: d for d in deliveries}
    assert by_channel["dashboard"].mode is ChannelMode.REAL
    assert by_channel["browser_push"].mode is ChannelMode.SIMULATED
    assert "no push was actually transmitted" in by_channel["browser_push"].detail


def test_whatsapp_and_zoho_are_not_offered_as_channels():
    """Both were adapter-shape-only stubs, removed outright (Phase 0a) —
    not offered, not just excluded from the default set."""
    report = ChannelOrchestrator.channel_report()
    assert "whatsapp" not in report
    assert "zoho_cliq" not in report
    assert "zoho_cliq" not in ChannelOrchestrator().channels
    assert "whatsapp" not in ChannelOrchestrator().channels


# ------------------------------------------------------------- lifecycle

def test_extended_lifecycle_transitions():
    S = AlertLifecycleStatus
    assert is_legal_alert_transition(S.CREATED, S.ROUTED)
    assert is_legal_alert_transition(S.ROUTED, S.DELIVERY_PENDING)
    assert is_legal_alert_transition(S.DELIVERY_PENDING, S.DELIVERED)
    assert is_legal_alert_transition(S.DELIVERED, S.ACKNOWLEDGED)
    assert is_legal_alert_transition(S.ACKNOWLEDGED, S.RESOLVED)
    # illegal
    assert not is_legal_alert_transition(S.DELIVERED, S.RESOLVED)
    assert not is_legal_alert_transition(S.RESOLVED, S.ACKNOWLEDGED)
    assert not is_legal_alert_transition(S.CREATED, S.DELIVERED)


def test_orchestrator_records_every_transition_for_audit():
    store = InMemoryAlertStore()
    alert = AlertOrchestrator(store).process(
        evaluate_material_changes(_case(), None)[0])
    tos = [t["to"] for t in alert.transitions]
    assert tos[:3] == ["created", "routed", "delivery_pending"]
    assert all(t["reason"] for t in alert.transitions)
    assert all(t["actor"] for t in alert.transitions)


def test_replay_run_alert_is_marked_simulated_not_real():
    """A REPLAY engine run is not a live operational event, regardless of
    how real its evidence_mode is."""
    store = InMemoryAlertStore()
    alert = AlertOrchestrator(store).process(
        evaluate_material_changes(_case(engine_mode="replay"), None)[0])
    assert alert.is_simulated is True
    assert alert.evidence_mode == "real"  # evidence stays honestly real
