import uuid
from typing import Optional, List
from datetime import datetime, timezone
from varuna_contracts.schemas import AssetTasking
from varuna_contracts.states import MissionState, MissionRecord
from varuna_missions.repository import InMemoryMissionRepository
from varuna_infra.authorization import AuditLog, Principal, authorize
from varuna_infra.rbac import Permission

class MissionService:
    def __init__(self, repo: InMemoryMissionRepository,
                 audit: AuditLog | None = None):
        self._repo = repo
        # Owned rather than injected-required so existing constructor call
        # sites keep working; the authorization CHECK is not optional, only
        # the choice of where its audit trail is collected.
        self._audit = audit or AuditLog()

    def create_mission(self, case_id: str, asset_id: str, tasking: AssetTasking) -> MissionRecord:
        mission = MissionRecord(
            mission_id=f"MSN-{uuid.uuid4().hex[:8].upper()}",
            case_id=case_id,
            asset_id=asset_id,
            state=MissionState.AVAILABLE,
        )
        self._repo.save(mission)
        return mission

    def reserve(self, mission_id: str) -> MissionRecord:
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")
        m.transition(MissionState.RESERVED)
        self._repo.save(m)
        return m

    def approve_and_assign(self, mission_id: str, approved_by: str, *,
                           principal: Principal) -> MissionRecord:
        """Human authorization gate. approved_by MUST be set.

        MISSION_TRANSITIONS (varuna_contracts/states.py) has no direct
        AVAILABLE -> ASSIGNED edge; a freshly-created (PROPOSED) mission is
        AVAILABLE and must pass through RESERVED first. Calling
        `m.transition(ASSIGNED)` straight from AVAILABLE was previously
        illegal and raised on every first-time approval. For a mission
        already RESERVED (e.g. re-approval after a prior release), the
        reserve step is skipped rather than attempted twice.

        `principal` is REQUIRED, not optional-with-a-default. This is the one
        operation in the system that dispatches a physical asset, and a
        default-valued authorization parameter is a fail-open: every caller
        that forgot to pass it would silently be treated as authorized. An
        automated caller that genuinely has no human behind it should pass
        `Principal.system()` and will be correctly REFUSED, because SYSTEM
        does not hold APPROVE_MISSION — that refusal is the two-step human
        approval requirement being enforced rather than merely documented.
        """
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")

        # Authorize BEFORE mutating anything. Ordering matters: a permission
        # check after a state transition leaves a partially-approved mission
        # behind on denial.
        authorize(principal, Permission.APPROVE_MISSION,
                  operation="mission.approve_and_assign",
                  subject_id=mission_id, audit=self._audit)

        # The approver of record must be the principal who actually
        # authorized. Allowing them to differ would let an authorized caller
        # write someone else's name into the permanent approval record, which
        # is exactly the forgery the audit trail exists to prevent.
        if approved_by != principal.principal_id:
            raise ValueError(
                f"approved_by {approved_by!r} does not match the authorizing "
                f"principal {principal.principal_id!r} — the approval record must "
                "name whoever actually authorized the dispatch"
            )

        if m.state is MissionState.AVAILABLE:
            m.transition(MissionState.RESERVED)
        m.human_approved_by = approved_by
        m.transition(MissionState.ASSIGNED)
        m.assigned_at = datetime.now(timezone.utc)
        self._repo.save(m)
        return m

    @property
    def audit_log(self) -> AuditLog:
        """Authorization decisions taken through this service, allow and deny."""
        return self._audit

    def transition(self, mission_id: str, new_state: MissionState, *, reason: Optional[str] = None) -> MissionRecord:
        m = self._repo.get(mission_id)
        if m is None:
            raise ValueError(f"Mission {mission_id} not found")
        m.transition(new_state)
        self._repo.save(m)
        return m

    def get(self, mission_id: str) -> Optional[MissionRecord]:
        return self._repo.get(mission_id)
        
    def list_by_case(self, case_id: str) -> List[MissionRecord]:
        return self._repo.list_by_case(case_id)
        
    def list_active(self) -> List[MissionRecord]:
        return self._repo.list_active()
