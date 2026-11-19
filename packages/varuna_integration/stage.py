"""
Stage result envelope shared by every Track-4 integration boundary.

`StageStatus` answers "did this stage run?"; `EvidenceMode` (carried separately,
on the value's own `EvidenceEnvelope`) answers "how real is what it produced?".
They are deliberately not collapsed into one enum: a stage that ran perfectly
on simulated inputs is PRODUCED/SIMULATED, and a stage that never ran is
NOT_YET_PRODUCED with no mode at all.

Nothing here may silently succeed. A boundary that cannot produce its output
returns `StageStatus.BLOCKED` (a real, named failure) or
`StageStatus.NOT_YET_PRODUCED` (the producer is not wired/available yet) — it
never substitutes a mock value and reports success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, TypeVar

from varuna_contracts.evidence import EvidenceMode

T = TypeVar("T")


class StageStatus(StrEnum):
    PRODUCED = "produced"
    NOT_YET_PRODUCED = "not_yet_produced"
    BLOCKED = "blocked"


@dataclass
class StageResult(Generic[T]):
    """What one pipeline stage produced, plus why if it produced nothing."""

    stage: str
    status: StageStatus
    value: T | None = None
    evidence_mode: EvidenceMode | None = None
    reason: str | None = None
    runtime_seconds: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status is StageStatus.PRODUCED and self.value is None:
            raise ValueError(
                f"stage {self.stage!r}: PRODUCED requires a value — a stage that "
                f"produced nothing must report NOT_YET_PRODUCED or BLOCKED"
            )
        if self.status is not StageStatus.PRODUCED and self.reason is None:
            raise ValueError(
                f"stage {self.stage!r}: {self.status.value} requires an explicit "
                f"reason — nothing may fail silently"
            )

    @property
    def produced(self) -> bool:
        return self.status is StageStatus.PRODUCED

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status.value,
            "evidence_mode": self.evidence_mode.value if self.evidence_mode else None,
            "reason": self.reason,
            "runtime_seconds": self.runtime_seconds,
            "detail": self.detail,
        }


def worst_mode(*modes: EvidenceMode | None) -> EvidenceMode | None:
    """Monotonic-worsening combination of evidence modes.

    UNAVAILABLE dominates SIMULATED dominates REAL. Mirrors
    `EvidenceEnvelope.derive()`'s own rule so that a pipeline-level summary can
    never report a mode better than the worst contributing input. There is no
    parameter that overrides this, by design (ADR-0006).
    """
    present = [m for m in modes if m is not None]
    if not present:
        return None
    if EvidenceMode.UNAVAILABLE in present:
        return EvidenceMode.UNAVAILABLE
    if EvidenceMode.SIMULATED in present:
        return EvidenceMode.SIMULATED
    return EvidenceMode.REAL
