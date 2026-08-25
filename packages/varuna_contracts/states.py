"""
VARUNA GRID v2 — case and mission state.

Case state is FOUR INDEPENDENT DIMENSIONS, not one enum. Collapsing them was the
v1 mistake: "ATTRIBUTED" told you nothing about whether an asset was en route, and
"CLOSED" told you nothing about whether evidence was complete. Independent axes
make illegal combinations expressible — so `check_case_invariants` can catch them.
"""

from __future__ import annotations

from datetime import timezone, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MISSION_TRANSITIONS",
    "CaseLifecycle",
    "CaseStateVector",
    "EvidenceState",
    "InvestigationState",
    "MissionRecord",
    "MissionState",
    "OutcomeState",
    "ResponseState",
    "check_case_invariants",
    "is_legal_mission_transition",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ───────────────────────── The four case axes ─────────────────────────

class InvestigationState(StrEnum):
    DETECTED = "detected"
    TRIAGED = "triaged"
    VERIFIED = "verified"
    RECONSTRUCTED = "reconstructed"   # Phi built
    ATTRIBUTED = "attributed"         # NYAYA has run

    @property
    def rank(self) -> int:
        return ["detected", "triaged", "verified",
                "reconstructed", "attributed"].index(self.value)


class OutcomeState(StrEnum):
    PENDING = "pending"
    STRONG_LEAD = "strong_lead"
    WEAK_LEAD = "weak_lead"
    LATENT = "latent"
    NOT_DISTINGUISHABLE = "not_distinguishable"
    INCONCLUSIVE = "inconclusive"

    @property
    def supports_dispatch(self) -> bool:
        """Only these outcomes may justify committing a physical asset."""
        return self in (OutcomeState.STRONG_LEAD, OutcomeState.WEAK_LEAD,
                        OutcomeState.LATENT)


class ResponseState(StrEnum):
    NO_ACTION = "no_action"
    MONITORING = "monitoring"
    RECOMMENDATION_READY = "recommendation_ready"
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    ON_STATION = "on_station"
    SEARCHING = "searching"
    CONFIRMED = "confirmed"
    NEGATIVE = "negative"
    REASSIGNED = "reassigned"

    @property
    def is_committed(self) -> bool:
        """An asset is physically committed from ASSIGNED onward."""
        return self in (ResponseState.ASSIGNED, ResponseState.EN_ROUTE,
                        ResponseState.ON_STATION, ResponseState.SEARCHING)


class EvidenceState(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    COMPLETE = "complete"


class CaseLifecycle(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CaseStateVector(_Base):
    investigation: InvestigationState = InvestigationState.DETECTED
    outcome: OutcomeState = OutcomeState.PENDING
    response: ResponseState = ResponseState.NO_ACTION
    evidence: EvidenceState = EvidenceState.NONE
    lifecycle: CaseLifecycle = CaseLifecycle.OPEN
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def check_case_invariants(s: CaseStateVector) -> list[str]:
    """
    Return a list of violated invariants (empty == legal state).

    Call this on EVERY case write. A violation is a P0 bug, not a warning:
    it means a subsystem advanced a case into a state the architecture forbids.
    """
    v: list[str] = []

    if (
        s.outcome is not OutcomeState.PENDING
        and s.investigation.rank < InvestigationState.ATTRIBUTED.rank
    ):
        v.append("outcome set before investigation reached ATTRIBUTED")

    if s.response.is_committed and not s.outcome.supports_dispatch:
        v.append(f"asset committed ({s.response.value}) on non-dispatchable "
                 f"outcome ({s.outcome.value})")

    if s.response.is_committed and s.investigation.rank < InvestigationState.RECONSTRUCTED.rank:
        v.append("asset committed before Phi reconstruction")

    if s.lifecycle is CaseLifecycle.CLOSED and s.evidence is EvidenceState.NONE:
        v.append("case closed with no evidence preserved (PRAMAN violation)")

    if s.lifecycle is CaseLifecycle.CLOSED and s.response.is_committed:
        v.append("case closed while an asset is still committed")

    if s.outcome is OutcomeState.INCONCLUSIVE and s.response is ResponseState.CONFIRMED:
        v.append("CONFIRMED response on an INCONCLUSIVE outcome")

    return v


# ───────────────────────── Mission FSM ─────────────────────────

class MissionState(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    EN_ROUTE = "en_route"
    ON_STATION = "on_station"
    SEARCHING = "searching"
    CONTACT = "contact"
    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"
    REASSIGNED = "reassigned"
    COMPLETE = "complete"
    CLOSED = "closed"


MISSION_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.AVAILABLE:    frozenset({MissionState.RESERVED}),
    MissionState.RESERVED:     frozenset({MissionState.ASSIGNED, MissionState.AVAILABLE}),
    MissionState.ASSIGNED:     frozenset({MissionState.ACKNOWLEDGED, MissionState.REASSIGNED}),
    MissionState.ACKNOWLEDGED: frozenset({MissionState.EN_ROUTE, MissionState.REASSIGNED}),
    MissionState.EN_ROUTE:     frozenset({MissionState.ON_STATION, MissionState.REASSIGNED}),
    MissionState.ON_STATION:   frozenset({MissionState.SEARCHING, MissionState.REASSIGNED}),
    MissionState.SEARCHING:    frozenset({MissionState.CONTACT, MissionState.NOT_FOUND,
                                          MissionState.REASSIGNED}),
    MissionState.CONTACT:      frozenset({MissionState.CONFIRMED, MissionState.NOT_FOUND}),
    MissionState.CONFIRMED:    frozenset({MissionState.COMPLETE}),
    MissionState.NOT_FOUND:    frozenset({MissionState.COMPLETE, MissionState.REASSIGNED}),
    MissionState.REASSIGNED:   frozenset({MissionState.ASSIGNED, MissionState.CLOSED}),
    MissionState.COMPLETE:     frozenset({MissionState.CLOSED}),
    MissionState.CLOSED:       frozenset(),
}


def is_legal_mission_transition(src: MissionState, dst: MissionState) -> bool:
    return dst in MISSION_TRANSITIONS[src]


class MissionRecord(_Base):
    mission_id: str
    case_id: str
    asset_id: str
    state: MissionState = MissionState.AVAILABLE

    assigned_at: datetime | None = None
    acknowledged_at: datetime | None = None
    on_station_at: datetime | None = None
    closed_at: datetime | None = None

    # Human decisions and AI recommendations are stored SEPARATELY and never merged.
    recommended_by_system: bool = True
    human_approved_by: str | None = None      # user id — required before ASSIGNED
    human_override_reason: str | None = None

    state_history: list[tuple[str, datetime]] = Field(default_factory=list)

    def transition(self, dst: MissionState, *, at: datetime | None = None) -> None:
        if not is_legal_mission_transition(self.state, dst):
            raise ValueError(f"illegal mission transition {self.state.value} -> {dst.value}")
        if dst is MissionState.ASSIGNED and not self.human_approved_by:
            raise ValueError("ASSIGNED requires human_approved_by (authorization gate)")
        ts = at or datetime.now(timezone.utc)
        self.state_history = [*self.state_history, (dst.value, ts)]
        self.state = dst
