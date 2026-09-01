"""
VARUNA GRID — detection evidence + uncertainty contracts (ADR-0010).

The product principle these types exist to enforce: **NETRA is not the final
oracle.** NETRA produces SAR-derived *evidence*, which VARUNA reasons over
alongside other evidence, uncertainty, and contradictions. There is
deliberately no field on DetectionEvidenceEnvelope that says "this is oil" —
the closest thing is `classification`, which is NETRA's own claim, carried as
one input to fusion rather than as a verdict.

Measurement honesty is structural here, not a convention: every quantitative
field that could plausibly be fabricated is paired with a MeasurementStatus
so a consumer can tell a measured number from an inferred, simulated,
replayed, or absent one. A number with no status is not representable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from varuna_contracts.evidence import EvidenceEnvelope
from varuna_contracts.schemas import BBox, GeoPoint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class MeasurementStatus(StrEnum):
    """
    How a quantity came to exist. Distinct from EvidenceMode, which describes
    the *input data*; this describes *this particular number*.

    A run can be EvidenceMode.REAL and still carry INFERRED quantities (e.g. a
    morphology summary derived from a real mask), and a SIMULATED run can carry
    MEASURED quantities (genuinely measured off synthetic input). Collapsing the
    two would lose exactly the distinction operators need.
    """
    MEASURED = "measured"        # computed from actual data
    INFERRED = "inferred"        # derived/estimated, not directly observed
    SIMULATED = "simulated"      # synthetic value
    REPLAYED = "replayed"        # recorded real value played back
    UNAVAILABLE = "unavailable"  # not computed; no value exists


class Measured(_Base):
    """A quantity that knows how it came to exist."""
    value: float | None = None
    status: MeasurementStatus
    units: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _value_matches_status(self) -> Measured:
        if self.status is MeasurementStatus.UNAVAILABLE and self.value is not None:
            raise ValueError(
                "MeasurementStatus.UNAVAILABLE cannot carry a value — that is "
                "exactly the fabrication this type exists to prevent"
            )
        if self.status is not MeasurementStatus.UNAVAILABLE and self.value is None:
            raise ValueError(
                f"status={self.status.value} claims a value exists, but value is "
                "None; use UNAVAILABLE instead of a null measured quantity"
            )
        return self


class OODRisk(StrEnum):
    """Out-of-distribution risk relative to the model's training domain."""
    IN_DOMAIN = "in_domain"
    BORDERLINE = "borderline"
    OUT_OF_DOMAIN = "out_of_domain"
    UNKNOWN = "unknown"          # no OOD assessment was performed

    @property
    def rank(self) -> int:
        return {"in_domain": 0, "borderline": 1,
                "out_of_domain": 2, "unknown": 3}[self.value]


class DetectionEvidenceEnvelope(_Base):
    """
    Structured, provenance-carrying evidence produced by a perception run.

    This is NOT a verdict. `classification`/`confidence` are the detector's own
    claims; `quality`, `ood_risk` and `limitations` are what stop those claims
    from being read as ground truth downstream.
    """
    # Identity
    evidence_id: str
    case_id: str
    run_id: str | None = None

    # Model identity — all four, because a checkpoint hash alone does not tell
    # you how the input was prepared (the preprocessing gap named in
    # docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md section 8).
    model_id: str
    model_version: str
    checkpoint_sha256: str | None = None
    preprocessing_version: str | None = None
    channel_binding: list[str] = Field(default_factory=list)   # e.g. ["VV", "VH"]

    # Input identity
    input_asset_ids: list[str] = Field(default_factory=list)
    n_tiles: int = Field(0, ge=0)

    # Detector claim (an input to fusion, never a conclusion)
    classification: str | None = None
    confidence: Measured | None = None
    decision_threshold: Measured | None = None

    # Segmentation / morphology summaries
    segmentation_ref: str | None = None
    foreground_fraction: Measured | None = None
    n_connected_components: Measured | None = None
    area_km2: Measured | None = None
    centroid: GeoPoint | None = None
    bbox: BBox | None = None

    # Score distribution
    score_max: Measured | None = None
    score_mean: Measured | None = None
    score_p99: Measured | None = None

    # Quality / OOD
    ood_risk: OODRisk = OODRisk.UNKNOWN
    ood_rationale: str | None = None
    low_wind_context: Measured | None = None   # m/s, if forcing was available

    # Honesty
    limitations: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    envelope: EvidenceEnvelope

    @property
    def has_detection(self) -> bool:
        """True only when the detector actually returned a positive geometry."""
        return self.centroid is not None and self.classification is not None


class UncertaintyAssessment(_Base):
    """
    Component-level uncertainty. Deliberately NOT a single scalar: collapsing
    "the model was unsure", "the input was poor", "the evidence disagrees" and
    "nothing was available" into one number destroys the information an
    operator needs in order to decide what to *do* about it.
    """
    case_id: str
    model_confidence: Measured | None = None
    data_quality: Measured | None = None
    ood_risk: OODRisk = OODRisk.UNKNOWN
    evidence_agreement: Measured | None = None
    evidence_conflict_count: int = Field(0, ge=0)
    attribution_uncertainty: Measured | None = None
    forecast_uncertainty: Measured | None = None
    decision_confidence: Measured | None = None
    component_notes: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)

    # Components where a HIGHER value means MORE uncertainty. Everything else
    # in the scan below is "higher = better" and gets inverted.
    _WORSE_WHEN_HIGH = ("attribution_uncertainty", "forecast_uncertainty")

    @property
    def dominant_concern(self) -> str:
        """Which component most limits confidence. Names the concern, not a score."""
        if self.ood_risk is OODRisk.OUT_OF_DOMAIN:
            return "ood_risk"
        if self.evidence_conflict_count > 0:
            return "evidence_conflict"
        usable = (MeasurementStatus.MEASURED, MeasurementStatus.INFERRED,
                  MeasurementStatus.REPLAYED)
        candidates: list[tuple[str, float]] = []
        for name in ("model_confidence", "data_quality", "evidence_agreement",
                     "attribution_uncertainty", "forecast_uncertainty",
                     "decision_confidence"):
            m: Measured | None = getattr(self, name)
            if m is not None and m.value is not None and m.status in usable:
                worse = m.value if name in self._WORSE_WHEN_HIGH else 1.0 - m.value
                candidates.append((name, worse))
        if not candidates:
            return "insufficient_assessment"
        return max(candidates, key=lambda kv: kv[1])[0]
