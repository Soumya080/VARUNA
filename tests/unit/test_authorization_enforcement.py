"""
Authorization enforcement.

`has_permission()` was implemented and unit-tested from early in the project
and had ZERO production call sites — the permission table was correct and
never consulted. These tests cover the enforcement boundary that closes that
gap, at the service layer (not only in HTTP), so a non-HTTP caller cannot
bypass it.
"""
from __future__ import annotations

import pytest

from varuna_contracts.states import MissionState
from varuna_infra.authorization import (
    AuditLog, AuthorizationError, Principal, authorize,
)
from varuna_infra.rbac import Permission
from varuna_missions.repository import InMemoryMissionRepository
from varuna_missions.service import MissionService

pytestmark = pytest.mark.unit

OFFICER = Principal(principal_id="watch_officer_1", role="duty_officer")
ANALYST = Principal(principal_id="analyst_7", role="analyst")
READER = Principal(principal_id="viewer_2", role="read_only")


def _service() -> tuple[MissionService, str]:
    svc = MissionService(InMemoryMissionRepository())
    mission = svc.create_mission("CASE-1", "asset-1", tasking=None)
    return svc, mission.mission_id


# ---------------------------------------------------------- authorize() core

def test_authorize_raises_rather_than_returning_false():
    """
    A bool return is the shape that gets accidentally ignored at a call site.
    Denial must be impossible to overlook.
    """
    with pytest.raises(AuthorizationError):
        authorize(ANALYST, Permission.APPROVE_MISSION, operation="test.op")


def test_authorize_returns_an_audit_entry_on_success():
    entry = authorize(OFFICER, Permission.APPROVE_MISSION, operation="test.op")
    assert entry.allowed is True
    assert entry.principal_id == "watch_officer_1"


def test_denials_are_audited_not_only_successes():
    """A deny that leaves no trace is indistinguishable from a request never made."""
    audit = AuditLog()
    with pytest.raises(AuthorizationError):
        authorize(ANALYST, Permission.APPROVE_MISSION, operation="test.op",
                  subject_id="MSN-1", audit=audit)
    denials = audit.denials()
    assert len(denials) == 1
    assert denials[0].allowed is False
    assert denials[0].subject_id == "MSN-1"
    assert denials[0].role == "analyst"


def test_unknown_role_is_denied_not_defaulted():
    with pytest.raises(AuthorizationError):
        authorize(Principal(principal_id="x", role="wizard"),
                  Permission.APPROVE_MISSION, operation="test.op")


# ------------------------------------------------- mission approval boundary

def test_duty_officer_can_approve_a_mission():
    svc, mid = _service()
    mission = svc.approve_and_assign(mid, approved_by=OFFICER.principal_id,
                                     principal=OFFICER)
    assert mission.state is MissionState.ASSIGNED
    assert mission.human_approved_by == "watch_officer_1"


@pytest.mark.parametrize("principal", [ANALYST, READER], ids=["analyst", "read_only"])
def test_unauthorized_role_cannot_approve_a_mission(principal):
    svc, mid = _service()
    with pytest.raises(AuthorizationError):
        svc.approve_and_assign(mid, approved_by=principal.principal_id,
                               principal=principal)


def test_denied_approval_leaves_the_mission_untouched():
    """
    Authorization runs BEFORE any state mutation. A denial must not leave a
    half-approved mission behind.
    """
    svc, mid = _service()
    before = svc.get(mid).state
    with pytest.raises(AuthorizationError):
        svc.approve_and_assign(mid, approved_by=ANALYST.principal_id, principal=ANALYST)
    after = svc.get(mid)
    assert after.state is before
    assert after.human_approved_by is None


def test_system_principal_cannot_approve_a_mission():
    """
    The two-step human approval requirement, enforced as a permission rather
    than as a convention: an unattended automated pipeline physically cannot
    dispatch an asset.
    """
    svc, mid = _service()
    system = Principal.system()
    with pytest.raises(AuthorizationError):
        svc.approve_and_assign(mid, approved_by=system.principal_id, principal=system)
    assert svc.get(mid).state is not MissionState.ASSIGNED


def test_principal_is_required_and_has_no_permissive_default():
    """
    A default-valued authorization parameter would be a fail-open: every
    caller that forgot it would be silently treated as authorized.
    """
    svc, mid = _service()
    with pytest.raises(TypeError):
        svc.approve_and_assign(mid, approved_by="anyone")   # no principal=


def test_approver_of_record_must_be_the_authorizing_principal():
    """
    Otherwise an authorized caller could write someone else's name into the
    permanent approval record — the forgery the audit trail exists to prevent.
    """
    svc, mid = _service()
    with pytest.raises(ValueError, match="does not match the authorizing principal"):
        svc.approve_and_assign(mid, approved_by="someone_else", principal=OFFICER)
    assert svc.get(mid).state is not MissionState.ASSIGNED


def test_service_records_its_authorization_decisions():
    svc, mid = _service()
    svc.approve_and_assign(mid, approved_by=OFFICER.principal_id, principal=OFFICER)
    with pytest.raises(AuthorizationError):
        svc.approve_and_assign(mid, approved_by=ANALYST.principal_id, principal=ANALYST)
    entries = svc.audit_log.for_subject(mid)
    assert [e.allowed for e in entries] == [True, False]
    assert all(e.operation == "mission.approve_and_assign" for e in entries)


def test_approving_a_missing_mission_reports_not_found():
    svc, _ = _service()
    with pytest.raises(ValueError, match="not found"):
        svc.approve_and_assign("MSN-NOPE", approved_by=OFFICER.principal_id,
                               principal=OFFICER)
