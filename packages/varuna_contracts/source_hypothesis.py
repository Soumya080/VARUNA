"""
VARUNA GRID — source-hypothesis contracts (ADR-0010).

CHHAYA's output type. Deliberately separate from NYAYA's `AttributionResultV2`:
NYAYA answers "which *vessel* released this", CHHAYA answers the prior
question "what *kind of source* is this at all" (a vessel? a seep? the
coast?). Conflating them would let a confident vessel-attribution be produced
for a slick whose most likely source class is a natural seep.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from varuna_contracts.evidence import EvidenceEnvelope


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceClass(StrEnum):
    VESSEL_ASSOCIATED = "vessel_associated"
    COASTAL = "coastal"
    NATURAL_SEEP = "natural_seep"
    OTHER_ANTHROPOGENIC = "other_anthropogenic"
    UNKNOWN = "unknown"


class HypothesisMethod(StrEnum):
    """
    How a hypothesis set was produced. Exists so a deterministic engine can
    never be presented as a learned model — the distinction the product
    principle requires be visible to operators and reviewers.
    """
    DECLARED_LIKELIHOOD_RATIO = "declared_likelihood_ratio"
    LEARNED_MODEL = "learned_model"          # reserved; nothing uses this yet
    OPERATOR_ASSERTED = "operator_asserted"


class FactorContribution(_Base):
    """One named piece of reasoning, with its effect made explicit."""
    factor: str
    detail: str
    log_likelihood_ratio: float          # >0 supports, <0 opposes, 0 neutral
    evidence_ids: list[str] = Field(default_factory=list)
    measured: bool = True                # False = a declared assumption, not data


class SourceHypothesis(_Base):
    source_class: SourceClass
    posterior: float = Field(..., ge=0, le=1)
    prior: float = Field(..., ge=0, le=1)
    supporting: list[FactorContribution] = Field(default_factory=list)
    contradicting: list[FactorContribution] = Field(default_factory=list)
    rationale: str


class SourceHypothesisEnvelope(_Base):
    """
    CHHAYA's ranked source hypotheses for one case.

    `method` and `methodology_note` are required, not optional metadata: the
    contract's purpose is that no consumer can render this as a model output
    without also being able to see that it is not one.
    """
    case_id: str
    hypotheses: list[SourceHypothesis]
    method: HypothesisMethod
    methodology_note: str
    engine_version: str

    uncertainty_note: str | None = None
    insufficient_evidence: bool = False
    contradictions: list[str] = Field(default_factory=list)
    evidence_ids_considered: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    envelope: EvidenceEnvelope

    @model_validator(mode="after")
    def _posteriors_form_a_distribution(self) -> SourceHypothesisEnvelope:
        if not self.hypotheses:
            raise ValueError(
                "a SourceHypothesisEnvelope with no hypotheses is not an honest "
                "'unknown' — emit SourceClass.UNKNOWN at posterior 1.0 instead"
            )
        classes = [h.source_class for h in self.hypotheses]
        if len(classes) != len(set(classes)):
            raise ValueError("duplicate source_class in hypotheses")
        total = sum(h.posterior for h in self.hypotheses)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"posteriors sum to {total:.6f}, not 1.0 — a partition of the "
                "hypothesis space must be a probability distribution"
            )
        return self

    @property
    def top(self) -> SourceHypothesis:
        return max(self.hypotheses, key=lambda h: h.posterior)

    @property
    def is_discriminating(self) -> bool:
        """
        True when the top hypothesis is meaningfully ahead of the runner-up.
        Threshold mirrors the Validity Gate's existing `distinguishability`
        check (0.1) rather than inventing a second, unrelated cutoff.
        """
        if len(self.hypotheses) < 2:
            return True
        ranked = sorted(self.hypotheses, key=lambda h: h.posterior, reverse=True)
        return (ranked[0].posterior - ranked[1].posterior) >= 0.1
