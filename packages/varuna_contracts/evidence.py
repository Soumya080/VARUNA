"""
VARUNA GRID v2 — Universal Evidence Envelope.

THE locked cross-cutting contract. Every artifact produced by any major subsystem
carries an EvidenceEnvelope. It answers, for any value anywhere in the system:

    Where did this come from?  How much do we trust it?  How uncertain is it?
    Is it still valid?  What produced it, at what version?

ARCHITECTURAL INVARIANTS (do not break without an ADR):
  1. Trust and confidence are DIFFERENT. Trust is about the SOURCE. Confidence is
     about the MEASUREMENT. A trusted source can produce a low-confidence value;
     an untrusted source can produce a high-confidence one. Never collapse them.
  2. Raw evidence is never mutated. Influence weight (`w`) bounds how much a value
     may affect downstream inference WITHOUT changing the value itself.
  3. Uncertainty propagates. A subsystem consuming a DEGRADED input may not emit a
     TRUSTED output. Use `EvidenceEnvelope.derive()` — it enforces this.
  4. `validity_state` gates operational action. RESTRICTED/INCONCLUSIVE artifacts
     must never reach the Action Gateway.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import timezone, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AnomalyFlag",
    "CalibrationState",
    "DegradationState",
    "EnvelopedArtifact",
    "EvidenceEnvelope",
    "EvidenceMode",
    "Provenance",
    "QualityMetrics",
    "TrustState",
    "UncertaintyBlock",
    "ValidityState",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ───────────────────────── Trust / validity vocabulary ─────────────────────────

class TrustState(StrEnum):
    """Data Guard verdict on the SOURCE. Not about measurement quality."""
    TRUSTED = "trusted"
    DEGRADED = "degraded"        # usable, reduced influence, must be surfaced
    CONFLICTED = "conflicted"    # disagrees with a correlated source
    QUARANTINED = "quarantined"  # zero influence, retained as raw evidence only

    @property
    def max_influence(self) -> float:
        """Bounded Evidence Influence ceiling. NOT PPO. See ADR-0003."""
        return {
            TrustState.TRUSTED: 1.0,
            TrustState.DEGRADED: 0.6,
            TrustState.CONFLICTED: 0.3,
            TrustState.QUARANTINED: 0.0,
        }[self]

    @property
    def rank(self) -> int:
        return {"trusted": 0, "degraded": 1, "conflicted": 2, "quarantined": 3}[self.value]


class ValidityState(StrEnum):
    """Validity/Uncertainty Gate verdict. Gates operational action."""
    VALID = "valid"
    DEGRADED = "degraded"          # actionable with caveats shown to the officer
    RESTRICTED = "restricted"      # analysis only — never reaches Action Gateway
    INCONCLUSIVE = "inconclusive"  # first-class outcome, not an error

    @property
    def rank(self) -> int:
        return {"valid": 0, "degraded": 1, "restricted": 2, "inconclusive": 3}[self.value]

    @property
    def allows_operational_action(self) -> bool:
        return self in (ValidityState.VALID, ValidityState.DEGRADED)


class EvidenceMode(StrEnum):
    """
    Where this evidence actually came from, independent of TrustState.

    TrustState answers "how much should this influence a decision?" — a
    QUARANTINED real observation and a well-formed synthetic fixture can both
    be TRUSTED=false or true for unrelated reasons. EvidenceMode answers a
    different, non-negotiable question: "is this a measurement of the real
    world, a stand-in for one, or absent?"

    ADR-0006 governs this type. Its central rule:

        EvidenceMode can only WORSEN as evidence flows downstream, never
        improve. REAL -> SIMULATED -> UNAVAILABLE is the only direction of
        travel. No code path, and in particular no configuration flag or
        settings object, may construct or derive a SIMULATED/UNAVAILABLE
        input into a REAL output. See EvidenceEnvelope.derive() and
        tests/contract/test_evidence_mode.py.
    """
    REAL = "real"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"

    @property
    def rank(self) -> int:
        """0 = best (real), 2 = worst (unavailable). Monotonic derive() uses this."""
        return {"real": 0, "simulated": 1, "unavailable": 2}[self.value]


class DegradationState(StrEnum):
    NOMINAL = "nominal"
    PARTIAL_INPUT_LOSS = "partial_input_loss"
    FALLBACK_SOURCE = "fallback_source"       # e.g. climatology instead of forecast
    REDUCED_ENSEMBLE = "reduced_ensemble"     # M lowered under compute pressure
    STALE_INPUT = "stale_input"
    CACHED_REPLAY = "cached_replay"           # DEMO_MODE / offline replay

    @property
    def rank(self) -> int:
        order = ["nominal", "partial_input_loss", "fallback_source",
                 "reduced_ensemble", "stale_input", "cached_replay"]
        return order.index(self.value)


class CalibrationState(StrEnum):
    CALIBRATED = "calibrated"
    UNCALIBRATED = "uncalibrated"
    OUT_OF_DOMAIN = "out_of_domain"   # inputs outside the calibration fit domain
    NOT_APPLICABLE = "not_applicable"


class AnomalyFlag(StrEnum):
    """Emitted by Data Guard (source-level) and Flow Inspection (propagation-level)."""
    SCHEMA_MISMATCH = "schema_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    CRS_MISMATCH = "crs_mismatch"
    TEMPORAL_GAP = "temporal_gap"
    TEMPORAL_NONMONOTONIC = "temporal_nonmonotonic"
    SPATIAL_OUT_OF_BOUNDS = "spatial_out_of_bounds"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    STALE = "stale"
    PHYSICALLY_IMPLAUSIBLE = "physically_implausible"
    STATISTICAL_OUTLIER = "statistical_outlier"
    SOURCE_DRIFT = "source_drift"
    CROSS_SOURCE_CONFLICT = "cross_source_conflict"
    CORRELATED_SOURCE_BIAS = "correlated_source_bias"
    SUSPECTED_MANIPULATION = "suspected_manipulation"
    # Flow-inspection specific
    TRAJECTORY_DISCONTINUITY = "trajectory_discontinuity"
    IMPLIED_SPEED_IMPOSSIBLE = "implied_speed_impossible"
    PROBABILITY_NOT_NORMALISED = "probability_not_normalised"
    MULTIMODAL_FIELD = "multimodal_field"
    CONVERGENCE_FAILURE = "convergence_failure"
    STALE_DOWNSTREAM_OUTPUT = "stale_downstream_output"
    CROSS_MODULE_CONTRADICTION = "cross_module_contradiction"


# ───────────────────────── Envelope components ─────────────────────────

class Provenance(_Base):
    """Immutable lineage. Points at RAW artifacts that are never overwritten."""
    source_id: str                                   # "cmems.glorys12v1", "netra"
    source_version: str | None = None             # product/dataset version string
    raw_artifact_refs: list[str] = Field(default_factory=list)  # MinIO keys, never mutated
    retrieved_at: datetime | None = None
    adapter_id: str | None = None                 # which source adapter fetched it
    license: str | None = None
    citation: str | None = None
    notes: str | None = None


class QualityMetrics(_Base):
    """Measurement quality. Distinct from source trust."""
    completeness: float | None = Field(None, ge=0, le=1)
    freshness_seconds: float | None = Field(None, ge=0)
    spatial_coverage: float | None = Field(None, ge=0, le=1)
    resolution_m: float | None = Field(None, gt=0)
    ood_score: float | None = Field(None, ge=0, le=1)   # 1 = far out of distribution
    model_confidence: float | None = Field(None, ge=0, le=1)
    extra: dict[str, float] = Field(default_factory=dict)


class UncertaintyBlock(_Base):
    """
    Uncertainty MUST propagate. A point estimate with no uncertainty is a bug
    in any scientific subsystem.
    """
    representation: str = "none"     # "none"|"gaussian"|"lognormal"|"samples"|"field"|"interval"
    mean: float | None = None
    std: float | None = Field(None, ge=0)
    lower: float | None = None
    upper: float | None = None
    interval_confidence: float | None = Field(None, gt=0, lt=1)
    entropy: float | None = Field(None, ge=0)
    n_samples: int | None = Field(None, gt=0)
    sensitivity: dict[str, float] = Field(default_factory=dict)  # d(output)/d(assumption)

    @model_validator(mode="after")
    def _interval_ordered(self) -> UncertaintyBlock:
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("lower must be <= upper")
        return self


# ───────────────────────── The envelope ─────────────────────────

class EvidenceEnvelope(_Base):
    """
    Attached to EVERY major subsystem output. See module docstring for invariants.

    Construct downstream envelopes with `.derive()` — it enforces monotonic
    degradation, so a subsystem cannot silently upgrade a DEGRADED input into a
    TRUSTED output.
    """
    artifact_id: str
    case_id: str | None = None
    parent_artifact_ids: list[str] = Field(default_factory=list)

    produced_by: str                                  # "netra" | "prativartan" | ...
    model_version: str | None = None
    processing_version: str = "0.1.0"
    created_at: datetime = Field(default_factory=_utcnow)

    crs: str = "EPSG:4326"
    units: dict[str, str] = Field(default_factory=dict)   # {"distance": "km", ...}

    provenance: Provenance
    mode: EvidenceMode  # REQUIRED, no default — see EvidenceMode docstring / ADR-0006.
                        # Every producer must explicitly declare real vs. simulated
                        # vs. unavailable. A missing value is a construction error
                        # by design, not an oversight to patch with a default.
    trust: TrustState = TrustState.TRUSTED
    influence_weight: float = Field(1.0, ge=0.0, le=1.0)  # Bounded Evidence Influence
    quality: QualityMetrics = Field(default_factory=QualityMetrics)
    uncertainty: UncertaintyBlock = Field(default_factory=UncertaintyBlock)
    calibration_state: CalibrationState = CalibrationState.NOT_APPLICABLE
    validity_state: ValidityState = ValidityState.VALID
    degradation_state: DegradationState = DegradationState.NOMINAL
    anomaly_flags: list[AnomalyFlag] = Field(default_factory=list)

    content_hash: str | None = None                # sha256 of the payload bytes

    @model_validator(mode="after")
    def _influence_within_trust_ceiling(self) -> EvidenceEnvelope:
        ceiling = self.trust.max_influence
        if self.influence_weight > ceiling + 1e-9:
            raise ValueError(
                f"influence_weight {self.influence_weight} exceeds ceiling {ceiling} "
                f"for trust={self.trust.value} (Bounded Evidence Influence, ADR-0003)"
            )
        return self

    @model_validator(mode="after")
    def _cached_replay_cannot_claim_real(self) -> EvidenceEnvelope:
        """
        ADR-0006. A cached/offline replay (DEMO_MODE) is, by construction, not a
        live real-world measurement — it is a recording of one played back later.
        Reporting mode=REAL on it would let a demo look indistinguishable from a
        live run. Reject the combination outright rather than trust every future
        caller to remember not to do this.
        """
        if self.mode is EvidenceMode.REAL and self.degradation_state is DegradationState.CACHED_REPLAY:
            raise ValueError(
                "mode=REAL cannot be combined with degradation_state=CACHED_REPLAY "
                "(ADR-0006) — a cached replay is not a live real-world measurement"
            )
        return self

    # ── derivation ────────────────────────────────────────────────────────────

    def derive(
        self,
        *,
        artifact_id: str,
        produced_by: str,
        also_from: Sequence[EvidenceEnvelope] = (),
        model_version: str | None = None,
        processing_version: str = "0.1.0",
        quality: QualityMetrics | None = None,
        uncertainty: UncertaintyBlock | None = None,
        calibration_state: CalibrationState | None = None,
        add_flags: Sequence[AnomalyFlag] = (),
        degradation: DegradationState | None = None,
        validity: ValidityState | None = None,
    ) -> EvidenceEnvelope:
        """
        Build a downstream envelope from this one (plus any co-inputs).

        Degradation is MONOTONIC: the result is never more trusted, more valid, or
        less degraded than the worst input. Callers may push it further down
        (`validity=`, `degradation=`) but never up. This is the mechanism that
        makes "uncertainty must propagate" structural rather than aspirational.
        """
        inputs = [self, *also_from]

        worst_trust = max((e.trust for e in inputs), key=lambda t: t.rank)
        worst_validity = max((e.validity_state for e in inputs), key=lambda v: v.rank)
        worst_degradation = max((e.degradation_state for e in inputs), key=lambda d: d.rank)
        min_influence = min(e.influence_weight for e in inputs)

        # EvidenceMode (ADR-0006): monotonic worsening only, exactly like trust/
        # validity/degradation above. Deliberately no `mode=` override parameter
        # exists on this method — unlike `validity=`/`degradation=`, which callers
        # may push further down but never up, there is no legitimate reason for a
        # caller to touch mode at all. It is derived, never asserted, downstream
        # of the original producer. This is what makes "config cannot upgrade
        # provenance" a structural fact rather than a convention: there is no
        # parameter here through which a config value COULD flow even if someone
        # tried.
        derived_mode = max((e.mode for e in inputs), key=lambda m: m.rank)

        if validity is not None and validity.rank > worst_validity.rank:
            worst_validity = validity
        if degradation is not None and degradation.rank > worst_degradation.rank:
            worst_degradation = degradation

        merged_flags: list[AnomalyFlag] = []
        for e in inputs:
            for f in e.anomaly_flags:
                if f not in merged_flags:
                    merged_flags.append(f)
        for f in add_flags:
            if f not in merged_flags:
                merged_flags.append(f)

        merged_units: dict[str, str] = {}
        for e in inputs:
            merged_units.update(e.units)

        return EvidenceEnvelope(
            artifact_id=artifact_id,
            case_id=self.case_id,
            parent_artifact_ids=[e.artifact_id for e in inputs],
            produced_by=produced_by,
            model_version=model_version,
            processing_version=processing_version,
            crs=self.crs,
            units=merged_units,
            provenance=Provenance(
                source_id=produced_by,
                raw_artifact_refs=sorted({
                    r for e in inputs for r in e.provenance.raw_artifact_refs
                }),
                adapter_id=None,
            ),
            mode=derived_mode,
            trust=worst_trust,
            influence_weight=min(min_influence, worst_trust.max_influence),
            quality=quality or QualityMetrics(),
            uncertainty=uncertainty or UncertaintyBlock(),
            calibration_state=calibration_state or CalibrationState.NOT_APPLICABLE,
            validity_state=worst_validity,
            degradation_state=worst_degradation,
            anomaly_flags=merged_flags,
        )

    def with_content_hash(self, payload: bytes | str | dict[str, Any]) -> EvidenceEnvelope:
        """Attach a sha256 of the payload. PRAMAN requires this on sealed artifacts."""
        if isinstance(payload, dict):
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        elif isinstance(payload, str):
            raw = payload.encode()
        else:
            raw = payload
        self.content_hash = hashlib.sha256(raw).hexdigest()
        return self

    @property
    def is_actionable(self) -> bool:
        """Action Gateway precondition. Never bypass this check."""
        return (
            self.validity_state.allows_operational_action
            and self.trust is not TrustState.QUARANTINED
            and self.influence_weight > 0.0
        )


class EnvelopedArtifact(_Base):
    """Mixin base for any payload that must carry provenance. Subsystems subclass this."""
    envelope: EvidenceEnvelope
