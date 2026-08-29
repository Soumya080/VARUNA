"""
VARUNA GRID v2 — Operator Case Contract (read-only API/frontend view).

This module is a PROJECTION, not a business-logic layer. `OperatorCase` never
computes science, infers a missing value, or overrides provenance/validity —
it re-shapes what the real backend producers (NETRA, PRATIVARTAN, NYAYA, the
Validity Gate, PRAVAAH, ABHIYAN, Mission FSM, alerts) have already produced
into one stable, versioned, frontend-consumable object.

Two status vocabularies exist here, deliberately kept separate (do not merge
them into one enum):

  - `EvidenceMode` (varuna_contracts.evidence) — is this evidence a real
    measurement, a simulated stand-in, or absent? A PROVENANCE question.
  - `ProducerStatus` (this module) — has the backend stage that would produce
    this section actually run for this case yet? A WORKFLOW question. A
    section can be NOT_YET_PRODUCED regardless of what EvidenceMode its
    upstream inputs carry (e.g. PRAVAAH forecasting is a real, wired
    subsystem, but `CaseWorkflow` — packages/varuna_domain/case_workflow.py —
    does not call it as part of the per-case pipeline yet; that is a
    ProducerStatus fact, not an EvidenceMode fact).

No field on this contract is ever populated with a fabricated default (0.0,
None-as-zero, empty-string-as-answer). Where a real value does not exist,
`SectionEnvelope.status` and `.reason` say so explicitly and `.value` is
`None`. See docs/api/OPERATOR_CASE_CONTRACT_V1.md for the full field guide,
worked examples, and frontend field-mapping guidance.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from varuna_contracts.decision import AttributionResultV2, ValidityGateResult
from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.phi import PhiField
from varuna_contracts.schemas import (
    AssetTasking,
    BBox,
    ForwardForecast,
    SlickDetection,
    VesselType,
)
from varuna_contracts.states import MissionRecord

__all__ = [
    "OPERATOR_CASE_SCHEMA_VERSION",
    "AISCandidateView",
    "AlertDeliveryStatus",
    "AlertView",
    "EvidenceComponentView",
    "EvidenceHealthView",
    "ObservationView",
    "OperatorCase",
    "ProducerStatus",
    "ProvenanceView",
    "SectionEnvelope",
    "SystemStatusView",
]

OPERATOR_CASE_SCHEMA_VERSION = "v1"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ───────────────────────── Workflow-state vocabulary ─────────────────────────

class ProducerStatus(StrEnum):
    """
    Has the backend stage that would fill this section actually run for this
    case? Distinct from `EvidenceMode`, which describes the QUALITY of a
    value that *has* been produced. See module docstring.
    """
    NOT_YET_PRODUCED = "not_yet_produced"   # stage exists but has not run for this case
    PRODUCED = "produced"                    # a real value is present in `.value`
    BLOCKED = "blocked"                      # stage ran but a gate/precondition stopped it
    ERROR = "error"                          # stage ran and failed


class AlertDeliveryStatus(StrEnum):
    """
    Mirrors `varuna_alerts.protocol.DeliveryResult.status` plus the
    "not attempted yet" case. Never collapse SIMULATED into DELIVERED — the
    frontend must be able to tell a demo channel from a live one (ADR-0006's
    REAL/SIMULATED distinction, applied to delivery rather than evidence).
    """
    GENERATED = "generated"
    QUEUED = "queued"
    DELIVERED = "delivered"
    SIMULATED = "simulated"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


T = TypeVar("T")


class SectionEnvelope(BaseModel, Generic[T]):
    """
    Every major OperatorCase section is one of these, never a bare value.
    `status` and `reason` are populated even when `value` is None — a
    frontend must never have to infer "why is this empty?" from silence.
    """
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    status: ProducerStatus
    reason: str | None = None
    evidence_mode: EvidenceMode | None = None   # None only when status is NOT_YET_PRODUCED
    value: T | None = None


# ───────────────────────── Section value types ─────────────────────────
#
# Where a canonical typed contract already exists for a subsystem's output
# (SlickDetection, PhiField, AttributionResultV2, ValidityGateResult,
# ForwardForecast, AssetTasking, MissionRecord), OperatorCase reuses it
# directly inside a SectionEnvelope rather than redefining an equivalent
# shape. The types below fill the remaining gaps: raw case input has no
# existing contract, a bounded AIS summary is needed to keep the payload
# light (see docs, section "Performance"), and alert delivery needs a
# pydantic adapter over the `DeliveryResult` dataclass.

class ObservationView(_Base):
    """
    What was actually given to the case at ingest time
    (`CaseWorkflow.ingest()`). There is currently no canonical "raw SAR
    observation" contract wired into the per-case pipeline — NETRA scene
    ingestion is a separate, not-yet-wired stage (see `DetectionView`'s
    NOT_YET_PRODUCED note in the docs) — so this summarizes the slick-point
    input the pipeline does have, honestly, without inventing sensor
    metadata nobody supplied.
    """
    n_slick_points: int = Field(..., ge=0)
    n_tracks: int = Field(..., ge=0)
    obs_time_hours: float
    bbox: BBox | None = None


class AISCandidateView(_Base):
    """
    Bounded summary of one `VesselTrack` (varuna_contracts.schemas). The
    full point-by-point trajectory is NOT embedded here (see docs,
    "Performance") — the AIS artifact/track itself is the reference for
    that. This is AIS OBSERVATION only; NYAYA's attribution posterior for
    this vessel lives in `OperatorCase.attribution`, never here (section 13
    of the operator-case-contract task explicitly separates the two).
    """
    mmsi: str
    vessel_name: str | None = None
    vessel_type: VesselType = VesselType.UNKNOWN
    n_points: int = Field(..., ge=0)
    start_time: datetime
    end_time: datetime
    total_gap_minutes: float = Field(..., ge=0)
    max_gap_minutes: float = Field(..., ge=0)
    transponder_active: bool = True


class AlertView(_Base):
    """Adapter over `varuna_alerts.protocol.DeliveryResult` (a dataclass)."""
    channel: str
    recipient: str
    delivery_status: AlertDeliveryStatus
    reason: str
    is_simulated: bool
    idempotency_key: str
    timestamp: datetime


class EvidenceComponentView(_Base):
    """
    One row of the operator dashboard's evidence-health strip (SAR, AIS,
    model consistency, forcing, ...). `score` is `None` whenever no real
    computation backs it — never 0, which would read as "measured and bad"
    instead of "not measured".
    """
    component: str
    status: ProducerStatus
    score: float | None = Field(None, ge=0, le=1)
    reason: str | None = None
    evidence_mode: EvidenceMode | None = None
    observed_at: datetime | None = None


class EvidenceHealthView(_Base):
    components: list[EvidenceComponentView] = Field(default_factory=list)

    @property
    def overall_evidence_mode(self) -> EvidenceMode | None:
        """
        Worst (highest-rank) EvidenceMode across components with a known
        mode — the same monotonic-worsening rule `EvidenceEnvelope.derive()`
        uses elsewhere. Returns None only if no component has a mode yet.
        """
        modes = [c.evidence_mode for c in self.components if c.evidence_mode is not None]
        return max(modes, key=lambda m: m.rank) if modes else None


class ProvenanceView(_Base):
    """
    Lineage summary. Never includes credentials, tokens, or raw storage
    endpoints — only IDs and versions a caller can use to look further.
    """
    case_id: str
    artifact_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    processing_versions: dict[str, str] = Field(default_factory=dict)
    manifest_artifact_id: str | None = None
    generated_at: datetime


class SystemStatusView(_Base):
    """
    Overall case status, in the repository's OWN existing vocabulary
    (`varuna_domain.entities.CaseStatus`) — not a new, competing set of
    words invented for this contract (task section 22).
    """
    case_status: str            # varuna_domain.entities.CaseStatus value
    scientific_status: str      # varuna_domain.entities.ScientificStatus value
    error: str | None = None


# ───────────────────────── The contract ─────────────────────────

class OperatorCase(_Base):
    """
    Canonical, versioned, read-only projection of one VARUNA case for the
    future operator dashboard. See module docstring and
    docs/api/OPERATOR_CASE_CONTRACT_V1.md.
    """
    schema_version: str = OPERATOR_CASE_SCHEMA_VERSION
    case_id: str
    generated_at: datetime

    system_status: SystemStatusView

    observation: SectionEnvelope[ObservationView]
    detection: SectionEnvelope[SlickDetection]
    origin: SectionEnvelope[PhiField]
    ais: SectionEnvelope[list[AISCandidateView]]
    attribution: SectionEnvelope[AttributionResultV2]
    validity: SectionEnvelope[ValidityGateResult]
    forecast: SectionEnvelope[ForwardForecast]
    decision: SectionEnvelope[list[AssetTasking]]
    mission: SectionEnvelope[list[MissionRecord]]
    alerts: SectionEnvelope[list[AlertView]]

    evidence: EvidenceHealthView
    provenance: ProvenanceView
