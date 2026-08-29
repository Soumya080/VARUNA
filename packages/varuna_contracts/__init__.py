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
    "AISGap",
    "AISPoint",
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
    # evidence
    "EvidenceEnvelope",
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
    "OutcomeState",
    "PhiDiagnostics",
    # phi
    "PhiField",
    "PriorContribution",
    "Provenance",
    "QualityMetrics",
    "ResponseState",
    "SearchBox",
    "SensitivityBlock",
    "SlickClass",
    "SlickDetection",
    "SpatialMode",
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
