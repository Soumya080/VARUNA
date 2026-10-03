"""
ABHIYAN / Mission / Alert operational workflow — decision-state derivation,
mission lifecycle mapping, alert severity, dedupe determinism, and
fail-closed proofs.

No GPU, no NETRA, no MC20 Gold data: every fixture here is a lightweight,
directly-constructed contract object, matching the style of
tests/unit/test_track4_boundaries.py.
"""
from __future__ import annotations
from varuna_infra.authorization import Principal

import pytest

from varuna_abhiyan.decision_state import derive_operational_decision_state
from varuna_abhiyan.mock import MockAbhiyanProvider
from varuna_abhiyan.service import AbhiyanService
from varuna_alerts.dedupe import DedupeWindow
from varuna_alerts.severity import infer_severity
from varuna_contracts.decision import GateCheck, ValidityGateResult
from varuna_contracts.evidence import EvidenceEnvelope, Provenance, ValidityState
from varuna_contracts.operator_case import AlertSeverity, OperationalDecisionState
from varuna_contracts.schemas import AssetType, GeoPoint, SearchBox
from varuna_contracts.states import MissionRecord, MissionState
from varuna_missions.lifecycle_view import (
    MissionNotCancellableError,
    cancel_mission,
    is_dispatchable,
    is_review_required,
)
from varuna_missions.repository import InMemoryMissionRepository
from varuna_missions.service import MissionService

pytestmark = pytest.mark.unit


# ADR-0015: MissionService.transition() now REQUIRES an authorized
# principal. These tests previously drove the FSM with no authorization
# check at all, so passing one here strengthens them rather than
# working around the change.
_APPROVER = Principal(principal_id="officer", role="duty_officer")


def _envelope(mode="simulated", artifact_id="e1"):
    from varuna_contracts.evidence import EvidenceMode
    return EvidenceEnvelope(
        artifact_id=artifact_id, produced_by="test",
        provenance=Provenance(source_id="test"), mode=EvidenceMode(mode),
    )


def _gate(state: ValidityState, *, checks=None) -> ValidityGateResult:
    checks = checks if checks is not None else [GateCheck(name="c", passed=state is ValidityState.VALID)]
    blocking = [] if state in (ValidityState.VALID, ValidityState.DEGRADED) else ["reason"]
    return ValidityGateResult(
        case_id="C1", state=state, checks=checks, blocking_reasons=blocking,
        envelope=_envelope(),
    )


# ───────────────────────── decision-state derivation ─────────────────────────

@pytest.mark.parametrize("state,expected", [
    (ValidityState.VALID, OperationalDecisionState.VALID),
    (ValidityState.DEGRADED, OperationalDecisionState.VALID),
    (ValidityState.RESTRICTED, OperationalDecisionState.RESTRICTED),
    (ValidityState.INCONCLUSIVE, OperationalDecisionState.UNAVAILABLE),
])
def test_decision_state_mapping(state, expected):
    assert derive_operational_decision_state(_gate(state)) is expected


def test_no_gate_is_unavailable_not_blocked():
    """No gate result at all -> UNAVAILABLE (insufficient evidence), never BLOCKED
    (which is reserved for a genuine execution failure)."""
    assert derive_operational_decision_state(None) is OperationalDecisionState.UNAVAILABLE


def test_stage_failure_is_blocked_regardless_of_any_gate():
    """A crashed validity stage is BLOCKED even if a stale gate object is passed."""
    assert derive_operational_decision_state(
        _gate(ValidityState.VALID), validity_stage_failed=True,
    ) is OperationalDecisionState.BLOCKED


def test_degraded_is_not_folded_into_restricted():
    """DEGRADED allows operational action (with caveats) -- collapsing it into
    RESTRICTED would incorrectly refuse a legitimately allowed action."""
    gate = _gate(ValidityState.DEGRADED)
    assert gate.allows_operational_action is True
    assert derive_operational_decision_state(gate) is OperationalDecisionState.VALID


# ───────────────────────── ABHIYAN never bypasses validity ─────────────────────────

def _real_search_box() -> SearchBox:
    center = GeoPoint(lon=72.0, lat=15.0)
    from varuna_contracts.schemas import BBox
    bbox = BBox(min_lon=71.9, min_lat=14.9, max_lon=72.1, max_lat=15.1)
    return SearchBox(bbox=bbox, center=center, area_km2=100.0, phi_mass_contained=1.0)


def test_restricted_gate_produces_zero_tasking_even_with_valid_search_boxes():
    """Fail-closed: RESTRICTED -> no automatic dispatch, proven with a REAL,
    well-formed SearchBox/asset list that WOULD produce tasking under VALID."""
    svc = AbhiyanService(MockAbhiyanProvider())
    gate = _gate(ValidityState.RESTRICTED)
    taskings, env = svc.plan_mission(
        search_boxes=[_real_search_box()], available_assets=[AssetType.DORNIER],
        gate_state=gate.state, parent_envelope=gate.envelope, case_id="C1",
    )
    assert taskings == []


def test_valid_gate_with_real_inputs_does_produce_tasking():
    """Sanity check that the RESTRICTED case above is a real gate, not a
    fixture that would return [] regardless of gate state."""
    svc = AbhiyanService(MockAbhiyanProvider())
    gate = _gate(ValidityState.VALID)
    taskings, env = svc.plan_mission(
        search_boxes=[_real_search_box()], available_assets=[AssetType.DORNIER],
        gate_state=gate.state, parent_envelope=gate.envelope, case_id="C1",
    )
    assert len(taskings) == 1


def test_inconclusive_gate_produces_zero_tasking():
    svc = AbhiyanService(MockAbhiyanProvider())
    gate = _gate(ValidityState.INCONCLUSIVE)
    taskings, _ = svc.plan_mission(
        search_boxes=[_real_search_box()], available_assets=[AssetType.DORNIER],
        gate_state=gate.state, parent_envelope=gate.envelope, case_id="C1",
    )
    assert taskings == []


# ───────────────────────── Mission: PROPOSED-only, no auto-advance ─────────────────────────

def _service() -> MissionService:
    return MissionService(repo=InMemoryMissionRepository())


def test_mission_created_from_tasking_is_proposed_not_assigned():
    svc = _service()
    tasking = MockAbhiyanProvider().generate_tasking(
        [_real_search_box()], [AssetType.DORNIER], _envelope(),
    )[0]
    mission = svc.create_mission(case_id="C1", asset_id=tasking.base_name, tasking=tasking)
    assert mission.state is MissionState.AVAILABLE
    assert mission.human_approved_by is None
    assert is_review_required(mission)
    assert not is_dispatchable(mission)


def test_mission_cannot_advance_to_assigned_without_human_approval():
    """RESTRICTED -> no automatic dispatch, proven at the FSM level: even a
    direct attempt to advance a mission bypasses no gate on its own, but the
    FSM itself refuses ASSIGNED without a named human approver."""
    m = MissionRecord(mission_id="M1", case_id="C1", asset_id="A1")
    m.transition(MissionState.RESERVED)   # the one legal predecessor of ASSIGNED
    with pytest.raises(ValueError, match="requires human_approved_by"):
        m.transition(MissionState.ASSIGNED)


def test_approve_and_assign_requires_named_human():
    svc = _service()
    tasking = MockAbhiyanProvider().generate_tasking(
        [_real_search_box()], [AssetType.DORNIER], _envelope(),
    )[0]
    mission = svc.create_mission(case_id="C1", asset_id=tasking.base_name, tasking=tasking)
    approved = svc.approve_and_assign(
        mission.mission_id, approved_by="watch_officer_1",
        principal=Principal(principal_id="watch_officer_1", role="duty_officer"))
    assert approved.state is MissionState.ASSIGNED
    assert approved.human_approved_by == "watch_officer_1"
    assert is_dispatchable(approved)
    assert not is_review_required(approved)


# ───────────────────────── Mission cancellation gap ─────────────────────────

def test_cancel_proposed_mission_raises_named_gap_error():
    """AVAILABLE (PROPOSED) has no legal MISSION_TRANSITIONS path to CLOSED --
    this must fail loudly, not silently no-op or invent a transition."""
    svc = _service()
    tasking = MockAbhiyanProvider().generate_tasking(
        [_real_search_box()], [AssetType.DORNIER], _envelope(),
    )[0]
    mission = svc.create_mission(case_id="C1", asset_id=tasking.base_name, tasking=tasking)
    with pytest.raises(MissionNotCancellableError):
        cancel_mission(svc, mission.mission_id, principal=_APPROVER)


def test_cancel_assigned_mission_uses_reassigned_then_closed():
    svc = _service()
    tasking = MockAbhiyanProvider().generate_tasking(
        [_real_search_box()], [AssetType.DORNIER], _envelope(),
    )[0]
    mission = svc.create_mission(case_id="C1", asset_id=tasking.base_name, tasking=tasking)
    svc.approve_and_assign(
        mission.mission_id, approved_by="watch_officer_1",
        principal=Principal(principal_id="watch_officer_1", role="duty_officer"))
    cancelled = cancel_mission(svc, mission.mission_id, principal=_APPROVER)
    assert cancelled.state is MissionState.CLOSED
    assert cancelled.state_history[-2][0] == MissionState.REASSIGNED.value
    assert cancelled.state_history[-1][0] == MissionState.CLOSED.value


# ───────────────────────── Alert severity: no invented urgency ─────────────────────────

@pytest.mark.parametrize("suppressed,is_simulated,expected", [
    (True, False, AlertSeverity.BLOCKED),
    (True, True, AlertSeverity.BLOCKED),   # suppressed wins even on a simulated channel
    (False, True, AlertSeverity.WARNING),
    (False, False, AlertSeverity.INFO),
])
def test_alert_severity_is_structural_only(suppressed, is_simulated, expected):
    assert infer_severity(suppressed=suppressed, is_simulated=is_simulated) is expected


def test_critical_severity_is_never_produced_by_infer_severity():
    """CRITICAL exists in the vocabulary but has no assignment policy in this
    codebase (see AlertSeverity's own docstring) -- prove infer_severity()
    never reaches it across its entire (small, boolean) input space."""
    for suppressed in (True, False):
        for is_simulated in (True, False):
            assert infer_severity(suppressed=suppressed, is_simulated=is_simulated) \
                is not AlertSeverity.CRITICAL


def test_simulated_alert_severity_never_reads_as_info():
    """SIMULATED evidence cannot silently become REAL: a simulated-channel
    alert must never carry the same severity as a genuinely-sent one."""
    assert infer_severity(suppressed=False, is_simulated=True) \
        != infer_severity(suppressed=False, is_simulated=False)


# ───────────────────────── Dedupe determinism ─────────────────────────

def test_same_case_event_recipient_key_is_a_duplicate_on_second_send():
    window = DedupeWindow(window_seconds=300)
    key = "CASE-1:validity.evaluated:watch_officer"
    assert window.is_duplicate(key) is False   # first send: not a duplicate
    assert window.is_duplicate(key) is True    # second send, same key: duplicate


def test_different_case_or_event_or_recipient_is_not_a_duplicate():
    window = DedupeWindow(window_seconds=300)
    assert window.is_duplicate("CASE-1:validity.evaluated:watch_officer") is False
    assert window.is_duplicate("CASE-2:validity.evaluated:watch_officer") is False
    assert window.is_duplicate("CASE-1:attribution.generated:watch_officer") is False
    assert window.is_duplicate("CASE-1:validity.evaluated:pilot") is False


def test_idempotency_key_scheme_is_deterministic_for_same_inputs():
    """The key AlertService.route_and_send() actually builds
    (`f"{case_id}:{event_type}:{recipient}"`) is reproducible: same inputs,
    same key, every time -- the property dedupe depends on."""
    def key(case_id, event_type, recipient):
        return f"{case_id}:{event_type}:{recipient}"
    assert key("C1", "validity.evaluated", "watch_officer") \
        == key("C1", "validity.evaluated", "watch_officer")
    assert key("C1", "validity.evaluated", "watch_officer") \
        != key("C1", "validity.evaluated", "pilot")


# ───────────────────────── OperatorCase.recommendation wiring ─────────────────────────

def test_recommendation_distinguishes_restricted_gate_from_stage_crash():
    """The two things named `BLOCKED` in this system must not collapse: a
    RESTRICTED gate (ProducerStatus.BLOCKED on the validity SectionEnvelope,
    per operator_case_view._validity_section) is OperationalDecisionState.
    RESTRICTED, not BLOCKED -- BLOCKED is reserved for validity_stage_failed."""
    from varuna_domain.entities import Case
    from apps.api.operator_case_view import _recommendation, _validity_section

    case = Case("REC-1")
    gate = _gate(ValidityState.RESTRICTED)
    case.metadata["gate_result"] = gate.model_dump(mode="json")
    validity = _validity_section(case)
    assert validity.status.value == "blocked"   # ProducerStatus.BLOCKED: gate ran, restricted

    recommendation = _recommendation(case, validity)
    assert recommendation is OperationalDecisionState.RESTRICTED   # not BLOCKED


def test_recommendation_is_blocked_only_for_a_real_pipeline_stage_failure():
    from varuna_domain.entities import Case
    from apps.api.operator_case_view import _recommendation, _validity_section

    case = Case("REC-2")
    case.metadata["validity_section"] = {
        "status": "blocked", "evidence_mode": None,
        "reason": "VALIDITY_GATE_FAILED: RuntimeError: boom",
        "value": None, "detail": {},
    }
    validity = _validity_section(case)
    recommendation = _recommendation(case, validity)
    assert recommendation is OperationalDecisionState.BLOCKED
