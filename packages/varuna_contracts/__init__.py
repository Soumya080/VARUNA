"""
VARUNA GRID v2 — the locked contract package.

Every other package imports FROM here and never redefines these types.
Changing anything in this package requires an ADR (see docs/adr/).

  evidence.py  EvidenceEnvelope, trust/validity vocabulary, Bounded Evidence Influence
  states.py    case state vector (4 axes), mission FSM, invariant checker
  phi.py       structured Phi object with first-class diagnostics
  decision.py  attribution output, Validity/Uncertainty Gate
  schemas.py   v1 domain payloads (detections, AIS, forecasts, tasking, evidence packs)
"""

from varuna_contracts.decision import (
    AttributionResultV2,
    CandidateScore,
    DecisionState,
    GateCheck,
    GateReason,
    LatentFinding,
    PriorContribution,
    ValidityGateResult,
)
from varuna_contracts.evidence import (
    AnomalyFlag,
    CalibrationState,
    DegradationState,
    EnvelopedArtifact,
    EvidenceEnvelope,
    EvidenceMode,
    Provenance,
    QualityMetrics,
    TrustState,
    UncertaintyBlock,
    ValidityState,
)
from varuna_contracts.operator_case import (
    OPERATOR_CASE_SCHEMA_VERSION,
    AISCandidateView,
    AlertDeliveryStatus,
    AlertView,
    EvidenceComponentView,
    EvidenceHealthView,
    ObservationView,
    OperatorCase,
    ProducerStatus,
    ProvenanceView,
    SectionEnvelope,
    SystemStatusView,
)
from varuna_contracts.phi import (
    ConvergenceFlag,
    PhiDiagnostics,
    PhiField,
    SensitivityBlock,
    SpatialMode,
    TimeDistribution,
)
from varuna_contracts.schemas import (
    AISGap,
    AISPoint,
    AssetTasking,
    AssetType,
    BBox,
    DarkVesselDetection,
    EvidenceManifest,
    ForwardForecast,
    GeoPoint,
    LandfallPrediction,
    LookAlikeType,
    SearchBox,
    SlickClass,
    SlickDetection,
    VesselTrack,
    VesselType,
)
from varuna_contracts.states import (
    CaseLifecycle,
    CaseStateVector,
    EvidenceState,
    InvestigationState,
    MissionRecord,
    MissionState,
    OutcomeState,
    ResponseState,
    check_case_invariants,
    is_legal_mission_transition,
)

CONTRACT_VERSION = "2.0.0"

__all__ = [
    "CONTRACT_VERSION",
    "OPERATOR_CASE_SCHEMA_VERSION",
    "AISCandidateView",
    "AISGap",
    "AISPoint",
    "AlertDeliveryStatus",
    "AlertView",
    "AnomalyFlag",
    "AssetTasking",
    "AssetType",
    # decision
    "AttributionResultV2",
    "BBox",
    "CalibrationState",
    "CandidateScore",
    "CaseLifecycle",
    # states
    "CaseStateVector",
    "ConvergenceFlag",
    "DarkVesselDetection",
    "DecisionState",
    "DegradationState",
    "EnvelopedArtifact",
    "EvidenceComponentView",
    # evidence
    "EvidenceEnvelope",
    "EvidenceHealthView",
    "EvidenceManifest",
    "EvidenceMode",
    "EvidenceState",
    "ForwardForecast",
    "GateCheck",
    "GateReason",
    # domain payloads
    "GeoPoint",
    "InvestigationState",
    "LandfallPrediction",
    "LatentFinding",
    "LookAlikeType",
    "MissionRecord",
    "MissionState",
    "ObservationView",
    # operator_case
    "OperatorCase",
    "OutcomeState",
    "PhiDiagnostics",
    # phi
    "PhiField",
    "PriorContribution",
    "ProducerStatus",
    "Provenance",
    "ProvenanceView",
    "QualityMetrics",
    "ResponseState",
    "SearchBox",
    "SectionEnvelope",
    "SensitivityBlock",
    "SlickClass",
    "SlickDetection",
    "SpatialMode",
    "SystemStatusView",
    "TimeDistribution",
    "TrustState",
    "UncertaintyBlock",
    "ValidityGateResult",
    "ValidityState",
    "VesselTrack",
    "VesselType",
    "check_case_invariants",
    "is_legal_mission_transition",
]
