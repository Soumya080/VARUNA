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
    "AlertSeverity",
    "AlertView",
    "EvidenceComponentView",
    "EvidenceHealthView",
    "ObservationView",
    "OperationalDecisionState",
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


class AlertSeverity(StrEnum):
    """
    Structural severity, NOT an urgency judgment. INFO/WARNING/BLOCKED are
    derived purely from facts already computed elsewhere (was the send
    suppressed, did it reach a simulated channel). CRITICAL exists in this
    enum because the operator-case-contract task requires the vocabulary,
    but nothing in this codebase ever assigns it: there is no repository
    policy anywhere (varuna_alerts.materiality/freshness/role_router) that
    scores how urgent a real spill event is (proximity to shore, asset
    availability, volume, ...). Inventing that scoring here would be
    exactly the kind of fabricated safety-critical rule the task
    prohibits. See `varuna_alerts.severity.infer_severity()` and
    reports/mission/ABHIYAN_MISSION_ALERTS_REPORT.md, "Alert severity policy
    gap", for the explicit gap this leaves.
    """
    INFO = "info"
    WARNING = "warning"
    BLOCKED = "blocked"
    CRITICAL = "critical"


class OperationalDecisionState(StrEnum):
    """
    A DERIVED, LOSSY view over three already-canonical vocabularies —
    `ValidityState` (did the gate run, what did it conclude),
    `varuna_integration.stage.StageStatus` (did the stage execute), and
    `EvidenceMode` (was there real evidence to run on) — collapsed into the
    four labels an external "decision state" requirement asks for. It is
    NOT a fourth, independent state machine and never overrides any of the
    three it derives from; those remain the source of truth and stay fully
    visible via `OperatorCase.validity`.

    Mapping (see `varuna_abhiyan.decision_state.derive_operational_decision_state`
    for the implementation):

        ValidityState.VALID, ValidityState.DEGRADED  -> VALID
            Both allow operational action per `ValidityState.
            allows_operational_action`. DEGRADED is NOT folded into
            RESTRICTED: it means "actionable with caveats shown to the
            officer", which is operationally VALID, just qualified — the
            caveats themselves are untouched, in `ValidityGateResult.
            officer_visible_caveats`, not summarised away here.
        ValidityState.RESTRICTED                      -> RESTRICTED
        ValidityState.INCONCLUSIVE, gate is None       -> UNAVAILABLE
            INCONCLUSIVE is evidence that was insufficient to reach a
            conclusion — the same operational answer as "no gate result
            exists yet", so both map to UNAVAILABLE rather than BLOCKED.
        an actual StageStatus.BLOCKED (ABHIYAN/validity/upstream crashed
        or an integration break occurred)  -> BLOCKED
            Reserved for genuine execution failures, never for a
            successful gate that answered "no".

    `ValidityState.INCONCLUSIVE` and `ValidityState.DEGRADED` are real,
    first-class outcomes and are never hidden by this enum — this is a
    SUBSET view for a caller that only wants the four-way operational
    bucket, not a replacement for the full gate result.
    """
    VALID = "valid"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"
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
    """
    Case-scoped adapter over `varuna_alerts.protocol.DeliveryResult` (a
    dataclass). `idempotency_key` doubles as the deterministic dedupe
    identifier the same case+event+recipient always produces — reused
    verbatim from `varuna_alerts.dedupe.DedupeWindow`'s own key scheme
    rather than inventing a second ID.
    """
    channel: str
    recipient: str
    # The routed event_type (e.g. "validity.evaluated"), read from the
    # alerts stage's own detail. `None` for alerts assembled without that
    # detail available (DeliveryResult itself carries no event_type) —
    # honestly unknown, not guessed by parsing a channel-specific
    # idempotency_key format.
    category: str | None = None
    delivery_status: AlertDeliveryStatus
    severity: AlertSeverity
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
    # How this case's current run was EXECUTED (real / replay / simulated) —
    # varuna_domain.golden_case_engine.EngineMode, distinct from any
    # section's `evidence_mode` (which answers "how real is THIS evidence,"
    # not "how was this run produced"). None for a case produced by the
    # legacy varuna_domain.case_workflow.CaseWorkflow path, which has no such
    # concept. See ADR-0012.
    engine_mode: str | None = None


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

    # Always computable — even "the gate never ran" is a defined answer
    # (UNAVAILABLE), so this is not wrapped in a SectionEnvelope like the
    # sections above. See `OperationalDecisionState` for what this is and
    # is not: a derived, lossy VIEW over `validity` (never a second gate).
    recommendation: OperationalDecisionState

    evidence: EvidenceHealthView
    provenance: ProvenanceView
