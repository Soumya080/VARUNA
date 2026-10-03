"""
STEP 6: the alert lifecycle that did not exist before this task (see
docs/product/ALERT_OPERATIONAL_DIAGNOSTIC.md, item 6). `DeliveryResult`
already answers "did a send happen"; `AlertRecord` answers the separate,
previously-missing question "has an operator handled this material
condition yet." One `AlertRecord` correlates the one-or-more `DeliveryResult`
rows a single `route_and_send()` call produced for one case+event, rather
than inventing a second delivery mechanism.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from varuna_contracts.operator_case import AlertSeverity


class AlertLifecycleStatus(StrEnum):
    """Operator handling state. Distinct from `DeliveryStatus`, which
    describes whether a channel send succeeded, not whether a human has
    looked at it.

    Workstream A extends the original 4 states to the target architecture's
    7: ROUTED and DELIVERY_PENDING/DELIVERED make the orchestration phase
    observable, instead of an alert appearing to jump straight from creation
    to a human acknowledging it."""

    CREATED = "created"
    ROUTED = "routed"
    DELIVERY_PENDING = "delivery_pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


_LIFECYCLE_TRANSITIONS: dict[AlertLifecycleStatus, frozenset[AlertLifecycleStatus]] = {
    AlertLifecycleStatus.CREATED: frozenset({
        AlertLifecycleStatus.ROUTED,
        # A human may act the moment an alert exists in the cockpit, without
        # waiting for outbound channel orchestration to finish.
        AlertLifecycleStatus.ACKNOWLEDGED, AlertLifecycleStatus.ESCALATED,
    }),
    AlertLifecycleStatus.ROUTED: frozenset({
        AlertLifecycleStatus.DELIVERY_PENDING, AlertLifecycleStatus.DELIVERED,
        AlertLifecycleStatus.ACKNOWLEDGED, AlertLifecycleStatus.ESCALATED,
    }),
    AlertLifecycleStatus.DELIVERY_PENDING: frozenset({
        AlertLifecycleStatus.DELIVERED,
        AlertLifecycleStatus.ACKNOWLEDGED, AlertLifecycleStatus.ESCALATED,
    }),
    AlertLifecycleStatus.DELIVERED: frozenset({
        AlertLifecycleStatus.ACKNOWLEDGED, AlertLifecycleStatus.ESCALATED,
    }),
    AlertLifecycleStatus.ACKNOWLEDGED: frozenset({
        AlertLifecycleStatus.ESCALATED, AlertLifecycleStatus.RESOLVED,
    }),
    AlertLifecycleStatus.ESCALATED: frozenset({AlertLifecycleStatus.RESOLVED}),
    AlertLifecycleStatus.RESOLVED: frozenset(),
}


def is_legal_alert_transition(src: AlertLifecycleStatus, dst: AlertLifecycleStatus) -> bool:
    return dst in _LIFECYCLE_TRANSITIONS[src]


class AlertRecord(BaseModel):
    """Case-scoped, persisted alert. `deliveries` carries the raw
    `DeliveryResult` rows (as dicts — that dataclass has no pydantic
    contract, mirrored the same way `AlertView` already does in
    `apps/api/operator_case_view.py::_alerts_section`) that this alert
    correlates, so an operator can see exactly what was actually sent
    without a second lookup."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    alert_id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    case_id: str
    event_type: str
    severity: AlertSeverity
    reason: str
    is_simulated: bool
    evidence_mode: str | None = None
    deliveries: list[dict] = Field(default_factory=list)
    correlation_key: str
    # ---- Workstream A additions -------------------------------------
    #: Stable dedupe identity. See varuna_alerts.dedupe_identity.
    dedupe_key: str | None = None
    material_dimension: str | None = None
    #: Typed link to the mission this alert concerns, when it concerns one.
    #: Previously the mission id existed only inside a free-text body or as a
    #: bare string in `evidence_refs`, so a UI could not navigate alert ->
    #: mission without parsing prose.
    mission_id: str | None = None
    previous_value: Any = None
    current_value: Any = None
    severity_basis: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    routing: dict | None = None
    engine_mode: str | None = None
    #: Append-only operational transition log (Phase 3: every transition
    #: must be auditable).
    transitions: list[dict] = Field(default_factory=list)
    status: AlertLifecycleStatus = AlertLifecycleStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    escalated_by: str | None = None
    escalated_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
