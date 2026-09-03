import logging
import uuid
from typing import Any, Optional, List
from datetime import datetime, timezone
from varuna_contracts.evidence import ValidityState
from varuna_contracts.schemas import AssetTasking
from varuna_contracts.states import MissionState, MissionRecord
from varuna_missions.repository import InMemoryMissionRepository
from varuna_infra.authorization import AuditLog, Principal, authorize
from varuna_infra.rbac import Permission

logger = logging.getLogger(__name__)


class MissionService:
    def __init__(self, repo: InMemoryMissionRepository,
                 audit: AuditLog | None = None,
                 alert_service: Any = None, alert_lifecycle: Any = None,
                 alert_orchestrator: Any = None):
        self._repo = repo
        # Owned rather than injected-required so existing constructor call
        # sites keep working; the authorization CHECK is not optional, only
        # the choice of where its audit trail is collected.
        self._audit = audit or AuditLog()
        # STEP 7, Phase 5: optional — wires `mission.assigned` into the same
        # AlertService/AlertLifecycleService the pipeline already uses,
        # reusing varuna_alerts' architecture rather than a second alerting
        # path. Optional so every existing construction site (tests,
        # scripts) that doesn't pass these is unaffected.
        # Legacy collaborators, kept so existing construction sites still
        # work; `mission.assigned` now goes through the orchestrator instead.
        self._alert_service = alert_service
        self._alert_lifecycle = alert_lifecycle
        self._alert_orchestrator = alert_orchestrator

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
        self._raise_mission_assigned_alert(m)
        return m

    def _raise_mission_assigned_alert(self, mission: MissionRecord) -> None:
        """`mission.assigned` — the one material event only this method can
        produce, because the pipeline always creates missions un-approved.

        Routed through the SAME AlertOrchestrator as every other alert. It
        previously used the legacy `AlertService.route_and_send` +
        `AlertLifecycleService.sync_from_deliveries` path, which wrote records
        with a different correlation-key format (`case:event`) into the same
        store the orchestrator keys as `case|dimension|event|window`. That gave
        one case two parallel alert systems and produced alerts with no
        severity basis, no routing decision and no material dimension.

        Failures are logged, never swallowed: an alerting problem must not
        undo a real dispatch approval, but it must also not be invisible.
        """
        if self._alert_orchestrator is None:
            return
        try:
            from varuna_alerts.material_change import MaterialChange, MaterialDimension
            from varuna_contracts.operator_case import AlertSeverity

            change = MaterialChange(
                case_id=mission.case_id,
                dimension=MaterialDimension.MISSION_STATE,
                event_type="mission.assigned",
                previous=MissionState.RESERVED.value,
                current=mission.state.value,
                reason=(f"mission {mission.mission_id} authorised by "
                        f"{mission.human_approved_by} and assigned to "
                        f"{mission.asset_id}"),
                severity=AlertSeverity.HIGH,
                severity_basis=("a human authorised a physical asset dispatch — "
                                "the highest-consequence transition in the system"),
                evidence_refs=[str(mission.mission_id)],
                engine_mode="real",
                evidence_mode="real",
            )
            alert = self._alert_orchestrator.process(change)
            if alert is not None and hasattr(alert, "mission_id"):
                alert.mission_id = mission.mission_id
                self._alert_orchestrator._store.save(alert)
        except Exception as exc:
            logger.warning(
                "mission.assigned alert failed for %s: %s: %s",
                mission.mission_id, type(exc).__name__, exc,
            )

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
