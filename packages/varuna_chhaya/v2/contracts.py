"""CHHAYA v2 normalized vessel-candidate contract (Phase 2).

Additive to `varuna_contracts` — does not replace `DarkVesselDetection`
(v1's simpler, already-locked output type stays as-is for v1 callers). This
is CHHAYA-owned, not a locked cross-cutting contract, so it can evolve
without an ADR — but it still carries `EnvelopedArtifact` provenance, per the
governing evidence architecture.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from varuna_contracts.evidence import EnvelopedArtifact
from varuna_contracts.schemas import GeoPoint


class ScoreType(StrEnum):
    """What kind of number `VesselCandidate.vessel_score` is. Every consumer
    MUST branch on this rather than assume — see non-goal "invent calibrated
    probabilities"."""
    RELATIVE_PLAUSIBILITY = "relative_plausibility"   # the only kind produced today
    CALIBRATED_PROBABILITY = "calibrated_probability"  # not produced by any detector here


class VesselCandidate(EnvelopedArtifact):
    """One normalized SAR vessel candidate. Fields the detector/georeferencer
    could not determine are None — never a fabricated placeholder value."""

    candidate_id: str
    case_id: str
    scene_id: str

    # Geography — populated only after georeference.py validates it.
    position: GeoPoint | None = None
    geolocation_valid: bool
    geolocation_rejection_reason: str | None = None

    # Detector-native, in scene pixel space, kept for auditability.
    pixel_row: float
    pixel_col: float

    detector_source: str          # e.g. "cfar_ca_v1"
    detector_mode: str            # "classical" | "pretrained_neural"
    vessel_score: float           # detector-native statistic
    score_type: ScoreType = ScoreType.RELATIVE_PLAUSIBILITY

    length_estimate_m: float | None = None   # None unless the detector/georef supports it
    vessel_class: str | None = None          # None unless the detector supports classification

    source_artifact_id: str       # PRAMAN artifact ref for the scene this came from
    acquisition_time: datetime

    model_config = {"extra": "forbid"}


class VesselCandidateBatch(EnvelopedArtifact):
    case_id: str
    scene_id: str
    candidates: list[VesselCandidate] = Field(default_factory=list)
    detector_source: str
    detector_mode: str
    detector_available: bool
    rejected_geolocation_count: int = 0
