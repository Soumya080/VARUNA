"""
Mission-lifecycle view: maps the operational vocabulary an external task
description asked for (PROPOSED / REVIEW_REQUIRED / APPROVED / DISPATCHABLE
/ DISPATCHED / COMPLETED / CANCELLED / BLOCKED) onto the existing, LOCKED
`MissionState` FSM in `varuna_contracts.states` — WITHOUT introducing a
second, competing state machine. `MissionState` and `MISSION_TRANSITIONS`
remain the only stored truth; everything below is either a direct rename of
an existing legal state or a read-only predicate over one.

Mapping table (not a 1:1 equivalence — see notes):

    requested label     MissionState / derived predicate
    ----------------     ---------------------------------------------------
    PROPOSED          -> MissionState.AVAILABLE, human_approved_by is None
                          (`is_review_required()` below)
    REVIEW_REQUIRED   -> DERIVED, not stored: same as PROPOSED. There is no
                          separate "under review" state in MISSION_TRANSITIONS
                          — a mission is either AVAILABLE-and-unapproved (=
                          review required) or has already been moved to
                          ASSIGNED via `approve_and_assign()`. Modelled as a
                          predicate so there is exactly one source of truth.
    APPROVED          -> MissionState.ASSIGNED, gated behind
                          `human_approved_by` (already enforced by
                          `MissionRecord.transition()` — ASSIGNED without an
                          approver raises).
    DISPATCHABLE      -> DERIVED, not stored: same as APPROVED
                          (`is_dispatchable()` below) — "approved and ready
                          to move" is not a distinct MissionState from
                          ASSIGNED in the current FSM.
    DISPATCHED        -> MissionState.EN_ROUTE (asset physically moving).
    COMPLETED         -> MissionState.COMPLETE.
    BLOCKED           -> NOT a MissionState at all. "No mission was created"
                          is a `StageStatus.BLOCKED` fact about the pipeline
                          stage (see `varuna_integration.pipeline._mission`),
                          not a state any `MissionRecord` instance is ever
                          in. A MissionRecord only exists once it has
                          already been proposed.
    CANCELLED         -> NO CLEAN EQUIVALENT. See `cancel_mission()` below —
                          this is a genuine, unresolved policy gap, not
                          silently worked around.

Cancellation gap
-----------------
`MISSION_TRANSITIONS` (varuna_contracts/states.py) has no path from
AVAILABLE or RESERVED to CLOSED — an unapproved, not-yet-dispatched mission
CANNOT be cancelled in the current locked FSM. For a mission that has
already reached ASSIGNED or later, REASSIGNED -> CLOSED IS a legal path and
can serve as an interim "cancelled" proxy (`cancel_mission()` performs
exactly that two-step transition). Adding a genuine CANCELLED state (or a
legal AVAILABLE/RESERVED -> CLOSED transition) requires an ADR against
`varuna_contracts/states.py`, which this task does not authorize touching.
See reports/mission/ABHIYAN_MISSION_ALERTS_REPORT.md, "Mission cancellation
policy gap", for the explicit, unresolved decision this leaves for a
science/product owner.
"""
from __future__ import annotations

from varuna_contracts.states import MissionRecord, MissionState, is_legal_mission_transition
from varuna_missions.service import MissionService

__all__ = [
    "MissionNotCancellableError",
    "cancel_mission",
    "is_dispatchable",
    "is_review_required",
]


def is_review_required(mission: MissionRecord) -> bool:
    """PROPOSED, not yet approved: created but no human has signed off."""
    return mission.state is MissionState.AVAILABLE and mission.human_approved_by is None


def is_dispatchable(mission: MissionRecord) -> bool:
    """APPROVED and assigned, ready for the pilot to move — not yet EN_ROUTE."""
    return mission.state is MissionState.ASSIGNED and mission.human_approved_by is not None


class MissionNotCancellableError(Exception):
    """
    Raised by `cancel_mission()` for a mission in AVAILABLE or RESERVED —
    the locked FSM has no legal transition to CLOSED from either state. This
    is the cancellation policy gap surfacing as a loud, named error rather
    than a silent no-op or an invented transition.
    """
    def __init__(self, mission: MissionRecord):
        self.mission = mission
        super().__init__(
            f"Mission {mission.mission_id} is in state {mission.state.value}, which has "
            "no legal MISSION_TRANSITIONS path to CLOSED. Cancelling a PROPOSED/"
            "REVIEW_REQUIRED mission (AVAILABLE or RESERVED) is not currently possible "
            "without an ADR against varuna_contracts/states.py — see "
            "reports/mission/ABHIYAN_MISSION_ALERTS_REPORT.md, "
            "'Mission cancellation policy gap'."
        )


def cancel_mission(service: MissionService, mission_id: str, *,
                   principal, reason: str | None = None) -> MissionRecord:
    """
    Interim "CANCELLED" for a mission that has already been assigned or
    later: REASSIGNED -> CLOSED, both already-legal transitions
    (MISSION_TRANSITIONS). Raises `MissionNotCancellableError` for
    AVAILABLE/RESERVED missions rather than fabricating a transition the
    locked FSM does not define.
    """
    mission = service.get(mission_id)
    if mission is None:
        raise ValueError(f"Mission {mission_id} not found")
    if not is_legal_mission_transition(mission.state, MissionState.REASSIGNED):
        raise MissionNotCancellableError(mission)
    service.transition(mission_id, MissionState.REASSIGNED,
                       principal=principal, reason=reason)
    return service.transition(mission_id, MissionState.CLOSED,
                              principal=principal, reason=reason)
