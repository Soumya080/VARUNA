"""
VARUNA GRID v2 — attribution output and the Validity/Uncertainty Gate.

Two things v1 got wrong and this module fixes:

  1. "Confident" and "distinguishable" were conflated. A posterior can be sharply
     peaked and still not distinguish two vessels that both sat in the same lobe of
     Phi. `distinguishability` measures the SEPARATION between candidates; posterior
     measures belief. Both are reported.

  2. Nothing structurally prevented a low-quality inference from reaching an
     operational action. `ValidityGateResult` is now a mandatory checkpoint —
     the Action Gateway takes it, not the AttributionResult.
"""

from __future__ import annotations

from datetime import timezone, datetime
import enum
if not hasattr(enum, "StrEnum"):
    class _StrEnum(str, enum.Enum): pass
    enum.StrEnum = _StrEnum
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from varuna_contracts.evidence import (
    CalibrationState,
    EvidenceEnvelope,
    TrustState,
    ValidityState,
)
from varuna_contracts.schemas import GeoPoint, VesselType

__all__ = [
    "AttributionResultV2",
    "CandidateScore",
    "DecisionState",
    "GateCheck",
    "GateReason",
    "LatentFinding",
    "PriorContribution",
    "ValidityGateResult",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DecisionState(StrEnum):
    STRONG_LEAD = "strong_lead"
    WEAK_LEAD = "weak_lead"
    NOT_DISTINGUISHABLE = "not_distinguishable"   # candidates exist, cannot separate
    LATENT_SOURCE = "latent_source"
    INCONCLUSIVE = "inconclusive"                 # evidence insufficient at all


class LatentFinding(StrEnum):
    """
    CHHAYA must NOT jump straight to 'dark vessel'. These are different claims
    with different evidential weight, and conflating them is how a system ends up
    accusing a ship that was simply outside the scene footprint.
    """
    NO_PLAUSIBLE_VISIBLE_SOURCE = "no_plausible_visible_source"
    VISIBLE_SOURCES_EXIST_BUT_WEAK = "visible_sources_exist_but_weak"
    RADAR_CONTACT_WITHOUT_AIS = "radar_contact_without_ais"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"   # cannot conclude either way


class PriorContribution(_Base):
    """Published, inspectable. A defence lawyer can attack a black box; not a table."""
    gap_score: float = Field(0.0, ge=0, le=1)
    speed_anomaly: float = Field(0.0, ge=0, le=1)
    loiter_score: float = Field(0.0, ge=0, le=1)
    night_proximity: float = Field(0.0, ge=0, le=1)
    type_weight: float = Field(1.0, gt=0)
    combined: float = Field(1.0, gt=0)
    weights_version: str = "hand_tuned_v1"


class CandidateScore(_Base):
    mmsi: str
    vessel_name: str | None = None
    vessel_type: VesselType = VesselType.UNKNOWN

    path_integral: float = Field(..., ge=0)        # evidence contribution
    prior: PriorContribution                       # prior contribution
    likelihood: float = Field(..., ge=0)
    posterior: float = Field(..., ge=0, le=1)
    rank: int = Field(..., ge=1)

    closest_approach_km: float = Field(..., ge=0)
    time_at_closest_hours: float
    phi_mass_explained: float = Field(..., ge=0, le=1)

    ais_reliability: float = Field(1.0, ge=0, le=1)   # gap/interp-adjusted confidence
    influence_weight: float = Field(1.0, ge=0, le=1)  # Bounded Evidence Influence


class AttributionResultV2(_Base):
    case_id: str
    slick_id: str
    phi_id: str

    decision_state: DecisionState
    candidates: list[CandidateScore] = Field(default_factory=list)

    latent_probability: float = Field(..., ge=0, le=1)
    latent_finding: LatentFinding
    latent_inferred_point: GeoPoint | None = None

    # Belief vs separation — different questions, reported separately.
    top_posterior: float = Field(0.0, ge=0, le=1)
    top_gap: float = Field(0.0, ge=0, le=1)          # p(1st) - p(2nd)
    distinguishability: float = Field(..., ge=0, le=1)
    posterior_entropy: float = Field(..., ge=0, le=1)

    calibration_state: CalibrationState = CalibrationState.UNCALIBRATED
    calibration_version: str | None = None

    phi_quality_summary: str = ""
    phi_multimodal: bool = False
    n_candidates_screened: int = Field(..., ge=0)
    n_candidates_scored: int = Field(..., ge=0)

    envelope: EvidenceEnvelope
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _normalised(self) -> AttributionResultV2:
        ps = [c.posterior for c in self.candidates]
        if ps != sorted(ps, reverse=True):
            raise ValueError("candidates must be sorted by posterior descending")
        total = sum(ps) + self.latent_probability
        if self.candidates and abs(total - 1.0) > 1e-3:
            raise ValueError(f"posterior must sum to 1 with latent, got {total}")
        if self.decision_state is DecisionState.STRONG_LEAD and not self.candidates:
            raise ValueError("STRONG_LEAD requires at least one candidate")
        return self


# ───────────────────────── Validity / Uncertainty Gate ─────────────────────────

class GateReason(StrEnum):
    """
    Machine-readable classification for a GateCheck's outcome. ADR-0006.

    Complements, never replaces, GateCheck.detail — the free-text `detail`
    field stays as the officer-facing explanation; `reason_code` is what a
    caller can switch on without string-matching English sentences. Not
    every check populates a code (an existing passing check may leave it
    None), and not every code here is emitted by the current validity gate
    — some (e.g. ACTION_NOT_AUTHORIZED, TEMPORAL_JOIN_UNAVAILABLE) belong to
    gates implemented in a later tranche and exist here now so the contract
    doesn't need a second ADR when they land.
    """
    DATA_INVALID = "data_invalid"
    DATA_QUARANTINED = "data_quarantined"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    EVIDENCE_SIMULATED = "evidence_simulated"
    PHI_NOT_CONVERGED = "phi_not_converged"
    PHI_UNINFORMATIVE = "phi_uninformative"
    PHI_DIAGNOSTICS_UNAVAILABLE = "phi_diagnostics_unavailable"
    ATTRIBUTION_UNCERTAIN = "attribution_uncertain"
    ATTRIBUTION_NOT_DISTINGUISHABLE = "attribution_not_distinguishable"
    FORCING_INSUFFICIENT = "forcing_insufficient"
    TEMPORAL_JOIN_UNAVAILABLE = "temporal_join_unavailable"
    ACTION_NOT_AUTHORIZED = "action_not_authorized"


class GateCheck(_Base):
    name: str
    passed: bool
    observed: float | None = None
    threshold: float | None = None
    detail: str = ""
    reason_code: GateReason | None = None  # defaulted: existing extra="forbid"
                                            # consumers that construct GateCheck
                                            # without this field keep working.


class ValidityGateResult(_Base):
    """
    MANDATORY between NYAYA and any operational consumer (ABHIYAN, alerts, missions).

    The Action Gateway consumes THIS, never a raw AttributionResultV2. If
    `state.allows_operational_action` is False, no asset may be committed and no
    external alert may be dispatched — regardless of how confident the posterior is.
    """
    case_id: str
    state: ValidityState
    checks: list[GateCheck] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    officer_visible_caveats: list[str] = Field(default_factory=list)

    source_trust: TrustState = TrustState.TRUSTED
    envelope: EvidenceEnvelope
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _consistent(self) -> ValidityGateResult:
        failed = [c.name for c in self.checks if not c.passed]
        if failed and self.state is ValidityState.VALID:
            raise ValueError(f"state=VALID but checks failed: {failed}")
        if self.state in (ValidityState.RESTRICTED, ValidityState.INCONCLUSIVE) \
                and not self.blocking_reasons:
            raise ValueError(f"state={self.state.value} requires blocking_reasons")
        return self

    @property
    def allows_operational_action(self) -> bool:
        return (
            self.state.allows_operational_action
            and self.source_trust is not TrustState.QUARANTINED
        )
