"""
VARUNA — Alert Orchestrator (Workstream A, Phase 3-7).

MaterialChange -> dedupe -> enrich -> prioritise -> route -> deliver.

Reuses, rather than replaces:
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


def dedupe_bucket(now: datetime, window_seconds: int) -> int:
    """Discrete time bucket. Two events in the same bucket dedupe; the next
    bucket is a genuinely new alert."""
    return int(now.timestamp()) // max(1, window_seconds)


def dedupe_identity(change: MaterialChange, *, window: str | int = "run") -> str:
    """The documented dedupe rule (Phase 4).

    Identity = ``case_id | material_dimension | event_type | window``.

    Deliberately NOT the alert text (a reword would look like a new alert) and
    deliberately NOT the changed VALUE — the Material Change Engine has
    already decided the value moved *materially*, so the dimension is the
    right granularity.

    `window` is a discrete bucket, never a raw timestamp, so the same inputs
    always produce the same key.

    HISTORY: this defaulted to the literal string ``"run"`` and every caller
    used the default, which made it *lifetime suppression* rather than a
    window — a genuine second landfall prediction hours later was silently
    swallowed and the stale record returned. `AlertOrchestrator` now passes a
    real time bucket from an injected clock.
    """
    return f"{change.case_id}|{change.dimension.value}|{change.event_type}|{window}"


class AlertOrchestrator:
    #: Default dedupe window. Matches the 300 s already used by the
    #: pre-existing `varuna_alerts.dedupe.DedupeWindow`, so the system has one
    #: suppression interval rather than two competing ones.
    DEFAULT_WINDOW_SECONDS = 300

    def __init__(self, store: InMemoryAlertStore,
                 channels: ChannelOrchestrator | None = None,
                 audit: Any = None, praman: Any = None,
                 window_seconds: int = DEFAULT_WINDOW_SECONDS,
                 clock: Any = None):
        self._store = store
        self._channels = channels or ChannelOrchestrator()
        self._audit = audit
        self._praman = praman
        self._window_seconds = window_seconds
        # Injected so tests can pin time and keep replay deterministic.
        self._clock = clock or (lambda: datetime.now(timezone.utc))

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
    def process(self, change: MaterialChange, *,
                window: str | int | None = None) -> AlertRecord | None:
        """Run one material change through the full orchestration chain.

        Returns the AlertRecord (new or the deduped existing one), or None if
        materiality withheld the alert entirely.
        """
        # A caller may pin the window (tests, deterministic replay); otherwise
        # derive a real time bucket.
        bucket = (window if window is not None
                  else dedupe_bucket(self._clock(), self._window_seconds))
        key = dedupe_identity(change, window=bucket)

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

        # NOTE on materiality: `varuna_alerts.materiality.check_materiality()`
        # is NOT called here, and the block that pretended to is gone. It
        # computed a gate_state and then never used it, while its comment
        # claimed a restrictive validity gate still withheld outbound
        # alerting — a protection that did not exist. Materiality is now
        # enforced upstream instead: `evaluate_material_changes()` only emits
        # a change when the case's own state actually moved, and a case whose
        # gate blocks action (CASE-OOD) produces no changes at all, so no
        # alert reaches this point. Verified by
        # test_fail_closed_case_produces_no_material_change.

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

        from varuna_alerts.templates import render_subject

        deliveries = self._channels.deliver(
            alert_id=alert.alert_id,
            recipient_roles=[r.role.value for r in decision.recipients],
            subject=render_subject(alert), body=change.reason,
            # Passing the alert lets email/SMS use the real templates, which
            # state REAL vs DRILL in the body. An SMS reaching a duty officer
            # at 02:00 must never leave them guessing.
            alert=alert,
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
                    window: str | int | None = None) -> list[AlertRecord]:
        out = []
        for c in changes:
            a = self.process(c, window=window)
            if a is not None:
                out.append(a)
        return out
