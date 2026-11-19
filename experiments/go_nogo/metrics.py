"""Metrics for machine-readable go/no-go outputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrialMetrics:
    top1_correct: bool
    top3_correct: bool
    mrr: float
    truth_rank: int | None
    posterior_entropy: float
    candidate_count: int
    nearest_rank: int | None
    deterministic_rank: int | None


def rank_of(ranking: list[str], guilty_mmsi: str) -> int | None:
    try:
        return ranking.index(guilty_mmsi) + 1
    except ValueError:
        return None


def compute_metrics(
    varuna_ranking: list[str],
    nearest_ranking: list[str],
    deterministic_ranking: list[str],
    guilty_mmsi: str,
    posterior_entropy: float,
    candidate_count: int,
) -> TrialMetrics:
    rank = rank_of(varuna_ranking, guilty_mmsi)
    nearest = rank_of(nearest_ranking, guilty_mmsi)
    deterministic = rank_of(deterministic_ranking, guilty_mmsi)
    return TrialMetrics(
        top1_correct=rank == 1,
        top3_correct=rank is not None and rank <= 3,
        mrr=0.0 if rank is None else 1.0 / rank,
        truth_rank=rank,
        posterior_entropy=posterior_entropy,
        candidate_count=candidate_count,
        nearest_rank=nearest,
        deterministic_rank=deterministic,
    )
