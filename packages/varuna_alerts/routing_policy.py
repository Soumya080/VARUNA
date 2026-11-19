"""
VARUNA — policy-driven role routing (Workstream A, Phase 6).

Replaces nothing: `varuna_alerts.role_router.ROLE_ROUTING` already existed
and is still the legacy per-event table. This module adds the missing
pieces the target architecture requires — routing keyed on the material
DIMENSION and SEVERITY (not just an event-type string), an explicit
recipient object, and an auditable reason for every routing decision.

It deliberately does NOT "notify everyone": each rule names the roles that
have a reason to act, and a rule that matches nothing routes to the duty
officer only, with that fallback stated in the decision reason.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from varuna_alerts.material_change import MaterialDimension
from varuna_contracts.operator_case import AlertSeverity


class OperationalRole(StrEnum):
    """Operational roles from the target architecture. Distinct from
    `varuna_infra.rbac.Role`, which governs API PERMISSIONS: these describe
    who should be TOLD about something. The two are related but not the
    same, and conflating them would let a notification list silently grant
    authority. `rbac_role` below is the explicit, reviewable bridge."""

    DUTY_OFFICER = "duty_officer"
    SUPERVISOR = "supervisor"
    FIELD_OPERATOR = "field_operator"
    ENFORCEMENT = "enforcement"
    DG_SHIPPING = "dg_shipping"
    STATE_PCB = "state_pcb"


#: Which RBAC role (if any) an operational role corresponds to for
#: permission purposes. `None` = an external stakeholder with NO API
#: permissions at all; they can be notified but can never act.
ROLE_RBAC_BRIDGE: dict[OperationalRole, str | None] = {
    OperationalRole.DUTY_OFFICER: "duty_officer",
    OperationalRole.SUPERVISOR: "admin",
    OperationalRole.FIELD_OPERATOR: "field_operator",
    OperationalRole.ENFORCEMENT: None,
    OperationalRole.DG_SHIPPING: None,
    OperationalRole.STATE_PCB: None,
}


class AlertRecipient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: OperationalRole
    rbac_role: str | None = None
    reason: str


class RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    severity: str
    recipients: list[AlertRecipient] = Field(default_factory=list)
    matched_rule: str
    reason: str


#: dimension -> (minimum severity, roles, rule name). Evaluated in order;
#: every matching rule contributes its roles.
_RULES: list[tuple[MaterialDimension | None, AlertSeverity | None, list[OperationalRole], str]] = [
    (MaterialDimension.DETECTION_PRESENCE, None,
     [OperationalRole.DUTY_OFFICER], "new-detection-to-duty-officer"),
    (MaterialDimension.DETECTION_CONFIDENCE, None,
     [OperationalRole.DUTY_OFFICER], "detection-change-to-duty-officer"),
    (MaterialDimension.ORIGIN_POSITION, None,
     [OperationalRole.DUTY_OFFICER, OperationalRole.FIELD_OPERATOR],
     "origin-moved-affects-tasking"),
    (MaterialDimension.ATTRIBUTION_POSTERIOR, None,
     [OperationalRole.DUTY_OFFICER, OperationalRole.ENFORCEMENT],
     "attribution-is-enforcement-relevant"),
    (MaterialDimension.VALIDITY_STATE, None,
     [OperationalRole.DUTY_OFFICER, OperationalRole.SUPERVISOR],
     "validity-change-needs-supervisor-visibility"),
    (MaterialDimension.LANDFALL_PREDICTION, None,
     [OperationalRole.DUTY_OFFICER, OperationalRole.SUPERVISOR,
      OperationalRole.STATE_PCB, OperationalRole.DG_SHIPPING],
     "shoreline-impact-notifies-environmental-and-shipping-authorities"),
    (MaterialDimension.MISSION_STATE, None,
     [OperationalRole.DUTY_OFFICER, OperationalRole.FIELD_OPERATOR,
      OperationalRole.SUPERVISOR],
     "mission-change-affects-asset-and-command"),
]

#: Any CRITICAL alert additionally reaches the supervisor, regardless of
#: dimension — escalation of last resort.
_CRITICAL_ADDS = [OperationalRole.SUPERVISOR]


def route(dimension: MaterialDimension, severity: AlertSeverity) -> RoutingDecision:
    roles: list[OperationalRole] = []
    matched: list[str] = []

    for rule_dim, min_sev, rule_roles, name in _RULES:
        if rule_dim is not None and rule_dim != dimension:
            continue
        if min_sev is not None and severity != min_sev:
            continue
        for r in rule_roles:
            if r not in roles:
                roles.append(r)
        matched.append(name)

    if severity is AlertSeverity.CRITICAL:
        for r in _CRITICAL_ADDS:
            if r not in roles:
                roles.append(r)
        matched.append("critical-always-reaches-supervisor")

    if not roles:
        roles = [OperationalRole.DUTY_OFFICER]
        matched.append("fallback-duty-officer-only")
        reason = (f"no routing rule matched dimension {dimension.value!r}; routed to the "
                  "duty officer only rather than broadcasting to all roles")
    else:
        reason = (f"dimension {dimension.value!r} at severity {severity.value!r} matched "
                  f"{', '.join(matched)}")

    return RoutingDecision(
        dimension=dimension.value,
        severity=severity.value,
        recipients=[
            AlertRecipient(role=r, rbac_role=ROLE_RBAC_BRIDGE[r],
                           reason=f"selected by rule(s): {', '.join(matched)}")
            for r in roles
        ],
        matched_rule=", ".join(matched),
        reason=reason,
    )
