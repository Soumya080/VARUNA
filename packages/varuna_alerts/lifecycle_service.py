"""
STEP 6: operator response loop over `AlertRecord`. Mirrors
`varuna_missions.service.MissionService`'s authorization pattern exactly —
`authorize()` called before any mutation, `AuditLog` never defaulted away
silently (see docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md, item 12, for
the bug that pattern is copied specifically to avoid repeating).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from varuna_alerts.lifecycle import AlertLifecycleStatus, AlertRecord, is_legal_alert_transition
from varuna_alerts.lifecycle_store import InMemoryAlertStore
from varuna_alerts.protocol import DeliveryResult
from varuna_alerts.severity import infer_severity
from varuna_infra.authorization import AuditLog, Principal, authorize
from varuna_infra.rbac import Permission


class IllegalAlertTransitionError(ValueError):
    pass


class AlertLifecycleService:
    def __init__(self, store: InMemoryAlertStore, audit: AuditLog | None = None):
        self._store = store
        self._audit = audit or AuditLog()

    @property
    def audit_log(self) -> AuditLog:
        return self._audit

    def sync_from_deliveries(
        self, *, case_id: str, event_type: str, deliveries: Iterable[DeliveryResult],
        evidence_mode: str | None,
    ) -> Optional[AlertRecord]:
        """Correlate one `route_and_send()` call's `DeliveryResult`s into one
        `AlertRecord`, keyed by `case_id:event_type` (the dedup granularity
        `varuna_alerts.dedupe.DedupeWindow` already uses per-recipient,
        rolled up one level to "one material condition = one alert").
        Idempotent: calling this again for the same case+event updates the
        existing record's deliveries rather than creating a duplicate —
        this IS the "correlate instead of flooding" requirement (Phase 4),
        reusing this store rather than adding a second dedupe mechanism.
        Returns None if there is nothing to correlate (all sends were
        pure "none"/suppressed-before-routing placeholders).
        """
        results = [d for d in deliveries if d.channel not in ("none",)]
        if not results:
            return None

        correlation_key = f"{case_id}:{event_type}"
        existing = self._store.get_by_correlation_key(correlation_key)
        is_simulated = all(r.is_simulated for r in results) if results else True
        suppressed = all(r.status in ("suppressed", "expired") for r in results)
        severity = infer_severity(suppressed=suppressed, is_simulated=is_simulated)
        delivery_dicts = [
            {
                "channel": r.channel, "recipient": r.recipient, "status": r.status,
                "reason": r.reason, "is_simulated": r.is_simulated,
                "idempotency_key": r.idempotency_key,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in results
        ]

        if existing is not None:
            existing.deliveries = delivery_dicts
            existing.severity = severity
            existing.is_simulated = is_simulated
            existing.evidence_mode = evidence_mode
            self._store.save(existing)
            return existing

        record = AlertRecord(
            case_id=case_id, event_type=event_type, severity=severity,
            reason=results[0].reason or "material change detected",
            is_simulated=is_simulated, evidence_mode=evidence_mode,
            deliveries=delivery_dicts, correlation_key=correlation_key,
        )
        self._store.save(record)
        return record

    def list_by_case(self, case_id: str) -> List[AlertRecord]:
        return self._store.list_by_case(case_id)

    def get(self, alert_id: str) -> Optional[AlertRecord]:
        return self._store.get(alert_id)

    def _transition(
        self, alert_id: str, dst: AlertLifecycleStatus, *, principal: Principal,
        permission: Permission, actor_field: str, at_field: str,
    ) -> AlertRecord:
        alert = self._store.get(alert_id)
        if alert is None:
            raise ValueError(f"Alert {alert_id} not found")

        authorize(principal, permission, operation=f"alert.{dst.value}",
                  subject_id=alert_id, audit=self._audit)

        if not is_legal_alert_transition(alert.status, dst):
            raise IllegalAlertTransitionError(
                f"cannot move alert {alert_id} from {alert.status.value} to {dst.value}"
            )

        setattr(alert, actor_field, principal.principal_id)
        setattr(alert, at_field, datetime.now(timezone.utc))
        alert.status = dst
        self._store.save(alert)
        return alert

    def acknowledge(self, alert_id: str, *, principal: Principal) -> AlertRecord:
        return self._transition(
            alert_id, AlertLifecycleStatus.ACKNOWLEDGED, principal=principal,
            permission=Permission.ACKNOWLEDGE_ALERT,
            actor_field="acknowledged_by", at_field="acknowledged_at",
        )

    def escalate(self, alert_id: str, *, principal: Principal) -> AlertRecord:
        return self._transition(
            alert_id, AlertLifecycleStatus.ESCALATED, principal=principal,
            permission=Permission.ESCALATE_ALERT,
            actor_field="escalated_by", at_field="escalated_at",
        )

    def resolve(self, alert_id: str, *, principal: Principal) -> AlertRecord:
        return self._transition(
            alert_id, AlertLifecycleStatus.RESOLVED, principal=principal,
            permission=Permission.RESOLVE_ALERT,
            actor_field="resolved_by", at_field="resolved_at",
        )
