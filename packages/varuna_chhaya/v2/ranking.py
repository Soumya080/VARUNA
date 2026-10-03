"""Phase 6 — deterministic evidence ranking.

Produces RELATIVE_PLAUSIBILITY, never CALIBRATED_PROBABILITY_OF_GUILT (see
`contracts.ScoreType`). Deliberately excludes AIS-association state from the
plausibility score itself: whether a candidate is a genuine, well-evidenced
SAR contact and whether it is AIS-matched are two DIFFERENT facts, and
blending them into one number would double-count/conflate detection quality
with an unrelated categorical property — the same "no blind confidence-score
addition" principle documented in
`docs/research/VARUNA_INTELLIGENCE_SPEC.md` (Evidence Fusion). AIS state and
origin consistency are reported alongside the score, not folded into it.

Ranking is a min-max normalization over the detector's own score plus a
bounded contribution from origin spatial/temporal consistency when available
— a simple, fully deterministic, documented formula. Ties break on
`candidate_id` (lexicographic) so ranking is reproducible byte-for-byte
across runs on the same input, per Phase 6's determinism requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from varuna_chhaya.v2.ais_association import AISAssociationResult
from varuna_chhaya.v2.contracts import VesselCandidate
from varuna_chhaya.v2.origin_consistency import OriginConsistency

# Weight on the origin-field bonus relative to the (already normalized-0..1)
# detector score. Kept small and documented rather than tuned — origin
# consistency should nudge ranking, not dominate a genuine SAR detection.
ORIGIN_BONUS_WEIGHT = 0.25


@dataclass
class CandidateRankingEntry:
    candidate_id: str
    evidence_dimensions: dict[str, float | None]
    missing_evidence: list[str]
    relative_plausibility: float
    explanation: str
    rank: int = 0


def rank_candidates(
    candidates: list[VesselCandidate],
    origin_by_id: dict[str, OriginConsistency],
) -> list[CandidateRankingEntry]:
    if not candidates:
        return []

    scores = [c.vessel_score for c in candidates]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0  # avoid div-by-zero when every candidate scores identically

    entries: list[CandidateRankingEntry] = []
    for c in candidates:
        norm_detector = (c.vessel_score - lo) / span
        origin = origin_by_id.get(c.candidate_id)
        missing = list(origin.missing_evidence) if origin else ["origin_consistency_not_evaluated"]

        origin_bonus = 0.0
        if origin is not None and origin.spatial_consistency is not None:
            # Clip the raw (unbounded-below) spatial score into a 0..1 bonus
            # contribution — the raw, unclipped value stays visible in
            # evidence_dimensions for anyone who wants the full picture.
            origin_bonus = max(0.0, min(1.0, origin.spatial_consistency))
            if origin.temporal_consistency is not None:
                origin_bonus *= origin.temporal_consistency

        if not c.geolocation_valid:
            plausibility = 0.0
            explanation = "invalid geolocation — cannot be evidentially ranked"
        else:
            plausibility = (1 - ORIGIN_BONUS_WEIGHT) * norm_detector + ORIGIN_BONUS_WEIGHT * origin_bonus
            explanation = (
                f"detector_score={c.vessel_score:.2f} (normalized {norm_detector:.2f} within this scene's "
                f"candidate set) via {c.detector_source}; origin-consistency bonus={origin_bonus:.2f}"
                + (f"; missing: {', '.join(missing)}" if missing else "")
            )

        entries.append(CandidateRankingEntry(
            candidate_id=c.candidate_id,
            evidence_dimensions={
                "detector_score_raw": c.vessel_score,
                "detector_score_normalized": norm_detector,
                "spatial_consistency": origin.spatial_consistency if origin else None,
                "temporal_consistency": origin.temporal_consistency if origin else None,
                "course_consistency": origin.course_consistency if origin else None,
                "speed_consistency": origin.speed_consistency if origin else None,
            },
            missing_evidence=missing,
            relative_plausibility=plausibility,
            explanation=explanation,
        ))

    entries.sort(key=lambda e: (-e.relative_plausibility, e.candidate_id))
    for i, e in enumerate(entries, start=1):
        e.rank = i
    return entries
