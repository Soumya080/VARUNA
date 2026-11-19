"""
ABHIYAN's operational decision-state view.

`derive_operational_decision_state()` answers one narrow question: given
what the Validity Gate concluded (and whether the pipeline stage that would
have asked it even ran), what is the four-way operational bucket
(`OperationalDecisionState`: VALID / RESTRICTED / BLOCKED / UNAVAILABLE) an
external caller wants?

This is NOT a second gate. It never re-evaluates evidence, never overrides
`ValidityGateResult.state`, and never decides whether an action is allowed —
`ValidityGateResult.allows_operational_action` remains the one authority for
that. This function only translates an already-final gate result into a
smaller vocabulary. See `varuna_contracts.operator_case.
OperationalDecisionState` for the full mapping table and rationale (in
particular why DEGRADED folds into VALID rather than RESTRICTED, and why
INCONCLUSIVE folds into UNAVAILABLE rather than BLOCKED).
"""
from __future__ import annotations

from varuna_contracts.decision import ValidityGateResult
from varuna_contracts.evidence import ValidityState
from varuna_contracts.operator_case import OperationalDecisionState

__all__ = ["derive_operational_decision_state"]


def derive_operational_decision_state(
    gate: ValidityGateResult | None,
    *,
    validity_stage_failed: bool = False,
) -> OperationalDecisionState:
    """
    Args:
        gate: the real `ValidityGateResult`, or `None` if the validity stage
            has not produced one (never ran, or produced nothing yet).
        validity_stage_failed: True only for a genuine execution failure —
            the gate crashed or an upstream dependency broke (e.g. a
            pipeline's `StageStatus.BLOCKED` on the validity stage). This is
            what distinguishes BLOCKED from UNAVAILABLE. Left False, a
            missing gate is reported UNAVAILABLE (the safer, more common
            case: evidence was insufficient to evaluate at all) rather than
            assumed to be a crash. Deliberately a plain bool, not an import
            of `varuna_integration.stage.StageStatus` — this package must
            not depend on the orchestration layer that depends on it.

    ABHIYAN MUST NEVER BYPASS VALIDITY: this function is read-only over an
    already-computed `gate` and cannot be used to authorize an action by
    itself — a caller still must check `gate.allows_operational_action`
    (or, equivalently, check that the return value is VALID) before
    planning any tasking.
    """
    if validity_stage_failed:
        return OperationalDecisionState.BLOCKED

    if gate is None:
        return OperationalDecisionState.UNAVAILABLE

    if gate.state in (ValidityState.VALID, ValidityState.DEGRADED):
        return OperationalDecisionState.VALID
    if gate.state is ValidityState.RESTRICTED:
        return OperationalDecisionState.RESTRICTED
    # ValidityState.INCONCLUSIVE: a real, evaluated outcome — the gate ran
    # and concluded evidence is insufficient. Operationally indistinguishable
    # from "no gate result", so it maps to UNAVAILABLE rather than BLOCKED,
    # which is reserved for execution failures.
    return OperationalDecisionState.UNAVAILABLE
