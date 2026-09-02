"""Phase 7 — clean evidence handoff to NYAYA.

`ChhayaEvidenceHandoff` deliberately keeps every evidence dimension NYAYA
needs to distinguish as a SEPARATE field — SAR vessel evidence, AIS evidence,
origin consistency, temporal consistency, candidate ranking, coverage
quality, missing evidence — rather than pre-collapsing them into one score.
CHHAYA does not decide attribution here; it hands over structured evidence.
See `packages/varuna_nyaya/chhaya_bridge.py` for the (additive, minimal) NYAYA
consumption point — no existing NYAYA file is modified by this package.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from varuna_chhaya.v2.ais_association import AISAssociationResult, AISAssociationState
from varuna_chhaya.v2.contracts import VesselCandidate
from varuna_chhaya.v2.origin_consistency import OriginConsistency
from varuna_chhaya.v2.outcomes import ChhayaOutcome
from varuna_chhaya.v2.ranking import CandidateRankingEntry
from varuna_contracts.evidence import EnvelopedArtifact


class CandidateEvidenceRecord(BaseModel):
    """One candidate's full evidence bundle, exactly as NYAYA needs it —
    nothing pre-fused."""
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    sar_vessel_score: float
    sar_score_type: str
    ais_state: AISAssociationState
    ais_distance_km: float | None
    origin_spatial_consistency: float | None
    origin_temporal_consistency: float | None
    course_consistency: float | None
    speed_consistency: float | None
    relative_plausibility: float
    rank: int
    missing_evidence: list[str]


class ChhayaEvidenceHandoff(EnvelopedArtifact):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    scene_id: str
    outcome: ChhayaOutcome
    outcome_reason: str

    detector_source: str
    detector_mode: str
    detector_available: bool

    coverage_quality: float | None
    candidates: list[CandidateEvidenceRecord] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


def build_handoff(
    case_id: str,
    scene_id: str,
    outcome: ChhayaOutcome,
    outcome_reason: str,
    detector_source: str,
    detector_mode: str,
    detector_available: bool,
    coverage_quality: float | None,
    candidates: list[VesselCandidate],
    ais_results: dict[str, AISAssociationResult],
    origin_by_id: dict[str, OriginConsistency],
    ranking: dict[str, CandidateRankingEntry],
    envelope,
) -> ChhayaEvidenceHandoff:
    records: list[CandidateEvidenceRecord] = []
    top_missing: set[str] = set()

    for c in candidates:
        ais = ais_results.get(c.candidate_id)
        origin = origin_by_id.get(c.candidate_id)
        rank = ranking.get(c.candidate_id)
        missing = list(rank.missing_evidence) if rank else []
        top_missing.update(missing)

        records.append(CandidateEvidenceRecord(
            candidate_id=c.candidate_id,
            sar_vessel_score=c.vessel_score,
            sar_score_type=c.score_type.value,
            ais_state=ais.state if ais else AISAssociationState.INCONCLUSIVE_AIS_COVERAGE,
            ais_distance_km=ais.distance_km if ais else None,
            origin_spatial_consistency=origin.spatial_consistency if origin else None,
            origin_temporal_consistency=origin.temporal_consistency if origin else None,
            course_consistency=origin.course_consistency if origin else None,
            speed_consistency=origin.speed_consistency if origin else None,
            relative_plausibility=rank.relative_plausibility if rank else 0.0,
            rank=rank.rank if rank else 0,
            missing_evidence=missing,
        ))

    return ChhayaEvidenceHandoff(
        case_id=case_id,
        scene_id=scene_id,
        outcome=outcome,
        outcome_reason=outcome_reason,
        detector_source=detector_source,
        detector_mode=detector_mode,
        detector_available=detector_available,
        coverage_quality=coverage_quality,
        candidates=records,
        missing_evidence=sorted(top_missing),
        envelope=envelope,
    )
