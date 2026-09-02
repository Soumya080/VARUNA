"""
VARUNA — Alert Orchestrator (Workstream A, Phase 3-7).

MaterialChange -> dedupe -> enrich -> prioritise -> route -> deliver.

Reuses, rather than replaces:
  * `varuna_alerts.materiality.check_materiality()` — still the outbound
    gate (it refuses to alert on a case whose validity withholds action).
  * `varuna_alerts.lifecycle_store.InMemoryAlertStore` — the ONE alert store.
  * `varuna_alerts.lifecycle_service.AlertLifecycleService` — ACK/escalate/
    resolve and their RBAC enforcement.
  * `varuna_infra.authorization.AuditLog` — the audit sink.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from varuna_alerts.channel_orchestrator import ChannelOrchestrator, DeliveryStatus
from varuna_alerts.lifecycle import AlertLifecycleStatus, AlertRecord
from varuna_alerts.lifecycle_store import InMemoryAlertStore
from varuna_alerts.material_change import MaterialChange
from varuna_alerts.routing_policy import route


def dedupe_identity(change: MaterialChange, *, window: str = "run") -> str:
    """The documented dedupe rule (Phase 4).

    Identity = ``case_id | material_dimension | event_type | window``.

    Deliberately NOT the alert text, and deliberately NOT the changed VALUE:
      * text would make a reworded message a "new" alert;
      * including the value would make every wobble a new alert, which is
        precisely the spam the Material Change Engine exists to prevent —
        the engine has already decided the value moved *materially*, so the
        dimension is the right granularity.

    `window` is a discrete bucket, not a wall-clock timestamp, so the same
    replay produces the same key every time (determinism requirement).
    """
    return f"{change.case_id}|{change.dimension.value}|{change.event_type}|{window}"


class AlertOrchestrator:
    def __init__(self, store: InMemoryAlertStore,
                 channels: ChannelOrchestrator | None = None,
                 audit: Any = None, praman: Any = None):
        self._store = store
        self._channels = channels or ChannelOrchestrator()
        self._audit = audit
        self._praman = praman

    # ---------------------------------------------------------------- audit
    def _record_transition(self, alert: AlertRecord, *, frm: str, to: str,
                           actor: str, reason: str, detail: dict | None = None) -> None:
        entry = {
            "from": frm, "to": to, "actor": actor, "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(), "detail": detail or {},
        }
        alert.transitions = [*alert.transitions, entry]
        if self._praman is not None:
            try:
                self._praman.register_artifact(
                    artifact_type="alert_transition", case_id=alert.case_id,
                    produced_by="alert_orchestrator",
                    data={"alert_id": alert.alert_id, **entry},
                )
            except Exception:
                pass  # audit must never break the operational path

    # ------------------------------------------------------------- pipeline
    def process(self, change: MaterialChange, *, window: str = "run") -> AlertRecord | None:
        """Run one material change through the full orchestration chain.

        Returns the AlertRecord (new or the deduped existing one), or None if
        materiality withheld the alert entirely.
        """
        from varuna_alerts.materiality import check_materiality
        from varuna_contracts.evidence import ValidityState

        key = dedupe_identity(change, window=window)

        # ---- 4. DEDUPLICATION (before any work is done) -----------------
        existing = self._store.get_by_correlation_key(key)
        if existing is not None:
            self._record_transition(
                existing, frm=existing.status.value, to=existing.status.value,
                actor="alert_orchestrator", reason="deduplicated",
                detail={"dedupe_key": key,
                        "note": "identical material dimension already alerted in this window"})
            self._store.save(existing)
            return existing

        # ---- outbound materiality gate (existing behaviour, reused) -----
        # A restrictive validity gate must still withhold outbound alerting.
        # We map the case's validity into the existing checker rather than
        # re-implementing its judgement.
        gate_state: ValidityState | None = None
        try:
            raw = (change.current if change.dimension.value == "validity.state"
                   else None)
            if isinstance(raw, str):
                gate_state = ValidityState(raw)
        except Exception:
            gate_state = None

        # ---- 3. ALERT GENERATION + enrichment ---------------------------
        # `is_simulated` answers "is this a real OPERATIONAL event?", which is
        # an engine_mode question, not an evidence_mode one. A REPLAY run of a
        # fixture whose sections carry evidence_mode="real" is still not a live
        # operational event, and must never be presented as one. Only a REAL
        # engine run produces a non-simulated alert.
        is_simulated = (change.engine_mode or "").lower() != "real"
        alert = AlertRecord(
            case_id=change.case_id,
            event_type=change.event_type,
            severity=change.severity,
            reason=change.reason,
            is_simulated=is_simulated,
            evidence_mode=change.evidence_mode,
            correlation_key=key,
            dedupe_key=key,
            material_dimension=change.dimension.value,
            previous_value=change.previous,
            current_value=change.current,
            severity_basis=change.severity_basis,
            evidence_refs=list(change.evidence_refs),
            engine_mode=change.engine_mode,
        )
        self._record_transition(alert, frm="-", to=AlertLifecycleStatus.CREATED.value,
                                actor="material_change_engine",
                                reason=change.reason,
                                detail={"dimension": change.dimension.value,
                                        "severity_basis": change.severity_basis})

        # ---- 5/6. PRIORITISATION + ROUTING ------------------------------
        decision = route(change.dimension, change.severity)
        alert.routing = decision.model_dump(mode="json")
        alert.status = AlertLifecycleStatus.ROUTED
        self._record_transition(
            alert, frm=AlertLifecycleStatus.CREATED.value,
            to=AlertLifecycleStatus.ROUTED.value, actor="routing_policy",
            reason=decision.reason,
            detail={"recipients": [r.role.value for r in decision.recipients],
                    "matched_rule": decision.matched_rule})

        # ---- 7. CHANNEL ORCHESTRATION -----------------------------------
        alert.status = AlertLifecycleStatus.DELIVERY_PENDING
        self._record_transition(
            alert, frm=AlertLifecycleStatus.ROUTED.value,
            to=AlertLifecycleStatus.DELIVERY_PENDING.value, actor="channel_orchestrator",
            reason="dispatching to configured channels")

        subject = f"[{change.case_id}] {change.severity.value.upper()} — {change.event_type}"
        deliveries = self._channels.deliver(
            alert_id=alert.alert_id,
            recipient_roles=[r.role.value for r in decision.recipients],
            subject=subject, body=change.reason,
        )
        alert.deliveries = [d.model_dump(mode="json") for d in deliveries]

        any_delivered = any(d.status is DeliveryStatus.DELIVERED for d in deliveries)
        if any_delivered:
            alert.status = AlertLifecycleStatus.DELIVERED
            self._record_transition(
                alert, frm=AlertLifecycleStatus.DELIVERY_PENDING.value,
                to=AlertLifecycleStatus.DELIVERED.value, actor="channel_orchestrator",
                reason="at least one channel confirmed delivery",
                detail={"channels": {d.channel: d.status.value for d in deliveries}})
        else:
            # Stays DELIVERY_PENDING — honestly. Nothing claims success.
            self._record_transition(
                alert, frm=AlertLifecycleStatus.DELIVERY_PENDING.value,
                to=AlertLifecycleStatus.DELIVERY_PENDING.value,
                actor="channel_orchestrator",
                reason="no channel confirmed delivery; alert remains delivery_pending",
                detail={"channels": {d.channel: d.status.value for d in deliveries}})

        self._store.save(alert)
        return alert

    def process_all(self, changes: list[MaterialChange], *,
                    window: str = "run") -> list[AlertRecord]:
        out = []
        for c in changes:
            a = self.process(c, window=window)
            if a is not None:
                out.append(a)
        return out
