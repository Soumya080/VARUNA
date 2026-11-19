"""
VARUNA GRID — next-best-action contracts (ADR-0010).

The agentic layer's vocabulary. An action is selected because a *named piece
of evidence is missing, weak, or contradictory* — never because a score
crossed an unexplained threshold. `NextBestAction.because` is required for
exactly that reason: an action nobody can explain is an action nobody can
audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionKind(StrEnum):
    """
    What the system can decide to do next. Deliberately small and concrete:
    each maps to a capability that actually exists in this repository, so the
    loop can never propose an action nothing can execute.
    """
    INSPECT_DETECTION_QUALITY = "inspect_detection_quality"
    ASSESS_OOD = "assess_ood"
    EXPAND_AIS_SEARCH = "expand_ais_search"
    RUN_RECONSTRUCTION = "run_reconstruction"
    RUN_SOURCE_HYPOTHESIS = "run_source_hypothesis"
    CONSULT_MEMORY = "consult_memory"
    RESOLVE_CONTRADICTION = "resolve_contradiction"
    REQUEST_ADDITIONAL_EVIDENCE = "request_additional_evidence"
    ESCALATE_TO_OPERATOR = "escalate_to_operator"
    PROCEED_TO_DECISION = "proceed_to_decision"
    STOP_INSUFFICIENT_EVIDENCE = "stop_insufficient_evidence"

    @property
    def is_terminal(self) -> bool:
        return self in (ActionKind.PROCEED_TO_DECISION,
                        ActionKind.STOP_INSUFFICIENT_EVIDENCE,
                        ActionKind.ESCALATE_TO_OPERATOR)


class ActionOutcome(StrEnum):
    EXECUTED = "executed"
    NO_CHANGE = "no_change"          # ran, but produced no new evidence
    UNAVAILABLE = "unavailable"      # capability or data absent
    FAILED = "failed"
    PENDING = "pending"


class NextBestAction(_Base):
    """One selected action, with its full justification."""
    action_id: str
    case_id: str
    kind: ActionKind
    because: str                                  # the uncertainty that motivated it
    targets_uncertainty: str                      # named component, e.g. "ood_risk"
    required_evidence: list[str] = Field(default_factory=list)
    expected_effect: str
    priority: int = Field(..., ge=0)              # 0 = most urgent
    selected_at: datetime = Field(default_factory=_utcnow)


class ActionRecord(_Base):
    """What actually happened when an action was executed."""
    action: NextBestAction
    outcome: ActionOutcome
    result_summary: str
    evidence_added: list[str] = Field(default_factory=list)
    changed: bool = False
    error: str | None = None
    runtime_seconds: float | None = None
    executed_at: datetime = Field(default_factory=_utcnow)


class LoopPhase(StrEnum):
    OBSERVE = "observe"
    ASSESS = "assess"
    IDENTIFY_UNCERTAINTY = "identify_uncertainty"
    SELECT_ACTION = "select_action"
    EXECUTE = "execute"
    UPDATE_EVIDENCE = "update_evidence"
    REASSESS = "reassess"
    TERMINATE = "terminate"


class DecisionStep(_Base):
    """One turn of the loop, fully inspectable."""
    iteration: int = Field(..., ge=0)
    phase: LoopPhase
    note: str
    action: NextBestAction | None = None
    record: ActionRecord | None = None
    dominant_concern: str | None = None
    at: datetime = Field(default_factory=_utcnow)


class DecisionTrace(_Base):
    """
    The whole reasoning history for a case. This is what makes the agentic
    layer answerable to the question "why is this case in this state?" without
    reading source code.
    """
    case_id: str
    steps: list[DecisionStep] = Field(default_factory=list)
    terminal_action: ActionKind | None = None
    terminal_reason: str | None = None
    iterations: int = Field(0, ge=0)
    halted_on_budget: bool = False

    def render(self) -> str:
        """Plain-text trace for logs and the operator view."""
        lines = [f"Decision trace for case {self.case_id} ({self.iterations} iteration(s)):"]
        for s in self.steps:
            head = f"  [{s.iteration}] {s.phase.value}: {s.note}"
            lines.append(head)
            if s.action is not None:
                lines.append(f"        action={s.action.kind.value} "
                             f"because={s.action.because}")
            if s.record is not None:
                lines.append(f"        outcome={s.record.outcome.value} "
                             f"changed={s.record.changed} :: {s.record.result_summary}")
        if self.terminal_action is not None:
            lines.append(f"  TERMINAL: {self.terminal_action.value} — {self.terminal_reason}")
        if self.halted_on_budget:
            lines.append("  NOTE: halted on iteration budget, not on a terminal decision.")
        return "\n".join(lines)
