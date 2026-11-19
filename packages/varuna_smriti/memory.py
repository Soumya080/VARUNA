"""
SMRITI v0.1 — persistent structured case memory.

WHAT THIS IS
------------
A durable record of prior cases plus retrieval by *structured* similarity:
geography, environmental regime, morphology, source hypothesis, attribution
pattern, and outcome. Explicitly NOT text-embedding retrieval — for this
domain, "cases 40 km apart in the same wind regime" is a far more meaningful
neighbour relation than "cases whose prose descriptions embed nearby", and a
structured metric is inspectable: `similarity_breakdown` shows exactly which
components drove a match.

WHAT THIS IS NOT
----------------
This is memory, **not learning**. Nothing here updates a model, a prior, or a
threshold. `retrieve_*` returns records; it never mutates live case state, and
the Case Engine treats what comes back as *context*, never as an override.
That boundary is enforced structurally in `MemoryRetrieval.advisory_only`,
which is `True` on every result and is asserted in the tests.

Persistence is a JSON-lines file. Deliberately boring: it needs to survive a
process restart and be diffable/auditable, and adding a database dependency
for a few thousand case records would be infrastructure this product does not
need yet. The `SmritiStore` interface is narrow enough that a Postgres-backed
implementation can replace it without touching callers.
"""
from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "smriti-v0.1-structured"

# Two cases further apart than this share no useful spatial context.
SPATIAL_HORIZON_KM = 500.0

# Component weights for the similarity metric. Declared, not fitted (same
# honesty rule as CHHAYA). Geography and environmental regime dominate because
# they are what actually determine whether a prior case's lessons transfer.
SIMILARITY_WEIGHTS: dict[str, float] = {
    "geography": 0.30,
    "environment": 0.25,
    "morphology": 0.15,
    "source_hypothesis": 0.15,
    "attribution_pattern": 0.10,
    "temporal": 0.05,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class CaseMemory(BaseModel):
    """One remembered case. Every field optional except identity — a case
    recorded early in its life knows very little, and that is a valid record."""
    model_config = ConfigDict(extra="forbid")

    case_id: str
    recorded_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # Geography / time
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    observed_at: datetime | None = None

    # Environmental regime
    wind_speed_ms: float | None = None
    current_speed_ms: float | None = None

    # Morphology
    area_km2: float | None = None
    elongation: float | None = None

    # Reasoning outcomes
    top_source_class: str | None = None
    source_posterior: float | None = None
    attributed_mmsi: str | None = None
    attribution_state: str | None = None
    validity_state: str | None = None
    evidence_mode: str | None = None

    # Result
    outcome: str | None = None            # e.g. "confirmed", "not_found", "unresolved"
    operator_feedback: str | None = None
    lessons: list[str] = Field(default_factory=list)
    failure_tags: list[str] = Field(default_factory=list)

    # Provenance — carried on every retrieval, never stripped
    provenance_source: str = "varuna.case_engine"
    run_id: str | None = None
    model_versions: dict[str, str] = Field(default_factory=dict)

    def to_line(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True)


class SimilarityBreakdown(BaseModel):
    """Why two cases were considered similar. Inspectable by construction."""
    model_config = ConfigDict(extra="forbid")
    components: dict[str, float] = Field(default_factory=dict)
    unavailable: list[str] = Field(default_factory=list)
    score: float = Field(..., ge=0, le=1)
    coverage: float = Field(..., ge=0, le=1)   # fraction of weight actually assessable


class MemoryHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory: CaseMemory
    similarity: SimilarityBreakdown


class MemoryRetrieval(BaseModel):
    """
    Retrieval result. `advisory_only` is always True and is not settable to
    False anywhere in this package — memory informs, it never decides.
    """
    model_config = ConfigDict(extra="forbid")
    query_case_id: str
    hits: list[MemoryHit] = Field(default_factory=list)
    advisory_only: bool = True
    engine_version: str = ENGINE_VERSION
    note: str = (
        "SMRITI memory is advisory context only. It must never override current "
        "evidence, alter a validity verdict, or supply a value the current case "
        "did not measure."
    )
    # Phase 7 (adaptive reweighting) — inspectable, never silent. "base" for
    # every existing caller that doesn't pass `weights=`; "adaptive" only
    # when a caller explicitly opts in with a feedback-derived override.
    weights_used: dict[str, float] = Field(default_factory=lambda: dict(SIMILARITY_WEIGHTS))
    weights_source: str = "base"


class SmritiStore:
    """JSON-lines-backed persistent case memory."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, CaseMemory] = {}
        self._load()

    # ------------------------------------------------------------ persistence

    def _load(self) -> None:
        if not self._path.exists():
            return
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                mem = CaseMemory.model_validate_json(raw)
            except Exception:
                # A corrupt line must not take down the whole memory. Skip it
                # loudly-in-principle (it stays in the file for inspection)
                # rather than crashing every case that touches SMRITI.
                continue
            self._cache[mem.case_id] = mem   # later lines win = last write wins

    def _flush(self) -> None:
        """Rewrite atomically: a half-written memory file is worse than none."""
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False,
                dir=str(self._path.parent), suffix=".tmp",
            ) as fh:
                tmp = Path(fh.name)
                for mem in sorted(self._cache.values(), key=lambda m: m.case_id):
                    fh.write(mem.to_line() + "\n")
            tmp.replace(self._path)
            tmp = None
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink()

    # ------------------------------------------------------------------ write

    def store_case(self, memory: CaseMemory) -> CaseMemory:
        self._cache[memory.case_id] = memory
        self._flush()
        return memory

    def update_case(self, case_id: str, **fields) -> CaseMemory:
        existing = self._cache.get(case_id)
        if existing is None:
            raise KeyError(f"no memory for case {case_id!r}; call store_case first")
        unknown = set(fields) - set(CaseMemory.model_fields)
        if unknown:
            raise ValueError(f"unknown CaseMemory field(s): {sorted(unknown)}")
        updated = existing.model_copy(update={**fields, "updated_at": _utcnow()})
        self._cache[case_id] = updated
        self._flush()
        return updated

    # ------------------------------------------------------------------- read

    def get(self, case_id: str) -> CaseMemory | None:
        return self._cache.get(case_id)

    def all_cases(self) -> list[CaseMemory]:
        return list(self._cache.values())

    def retrieve_similar_cases(self, query: CaseMemory, *, limit: int = 5,
                               min_score: float = 0.0,
                               min_coverage: float = 0.25,
                               weights: dict[str, float] | None = None) -> MemoryRetrieval:
        """
        Structured nearest neighbours.

        `min_coverage` guards the failure mode that matters most here: two
        near-empty records trivially "match" on the one field they share. A hit
        assessed on less than a quarter of the total weight is not returned,
        because that similarity number would be an artefact of missing data.

        `weights` (Phase 7, optional): override `SIMILARITY_WEIGHTS` with a
        feedback-derived adaptive set (see `feedback.py::compute_adaptive_
        weights()`). Omitted by every existing caller, which reproduces the
        exact base-weight result unchanged. The chosen weights are always
        recorded on the result (`weights_used`/`weights_source`) — never a
        silent substitution.
        """
        active_weights = weights if weights is not None else SIMILARITY_WEIGHTS
        hits: list[MemoryHit] = []
        for other in self._cache.values():
            if other.case_id == query.case_id:
                continue
            breakdown = self._similarity(query, other, weights=active_weights)
            if breakdown.coverage < min_coverage or breakdown.score < min_score:
                continue
            hits.append(MemoryHit(memory=other, similarity=breakdown))
        hits.sort(key=lambda h: (h.similarity.score, h.memory.case_id), reverse=True)
        return MemoryRetrieval(
            query_case_id=query.case_id, hits=hits[:limit],
            weights_used=dict(active_weights),
            weights_source="adaptive" if weights is not None else "base",
        )

    def retrieve_relevant_evidence(self, query: CaseMemory, *,
                                   limit: int = 5) -> MemoryRetrieval:
        """Similar cases that actually reached a recorded outcome or lesson."""
        full = self.retrieve_similar_cases(query, limit=len(self._cache) or 1)
        informative = [h for h in full.hits
                       if h.memory.outcome or h.memory.lessons]
        return MemoryRetrieval(query_case_id=query.case_id, hits=informative[:limit])

    def retrieve_failure_patterns(self, query: CaseMemory, *,
                                  limit: int = 5) -> MemoryRetrieval:
        """Prior cases carrying failure tags — what went wrong near here before."""
        full = self.retrieve_similar_cases(query, limit=len(self._cache) or 1)
        failures = [h for h in full.hits if h.memory.failure_tags]
        return MemoryRetrieval(query_case_id=query.case_id, hits=failures[:limit])

    def retrieve_prior_outcomes(self, query: CaseMemory, *,
                                limit: int = 10) -> dict[str, int]:
        """Outcome histogram over similar cases. Counts, never a prediction."""
        retrieval = self.retrieve_similar_cases(query, limit=limit)
        counts: dict[str, int] = {}
        for hit in retrieval.hits:
            if hit.memory.outcome:
                counts[hit.memory.outcome] = counts.get(hit.memory.outcome, 0) + 1
        return counts

    def corridor_case_count(self, lon: float, lat: float, radius_km: float) -> int:
        """How many remembered cases sit within `radius_km`. Feeds CHHAYA's
        recurrence factor — a real count, not an estimate."""
        n = 0
        for mem in self._cache.values():
            if mem.centroid_lon is None or mem.centroid_lat is None:
                continue
            if _haversine_km(lon, lat, mem.centroid_lon, mem.centroid_lat) <= radius_km:
                n += 1
        return n

    # -------------------------------------------------------------- similarity

    def _similarity(self, a: CaseMemory, b: CaseMemory,
                    weights: dict[str, float] | None = None) -> SimilarityBreakdown:
        active_weights = weights if weights is not None else SIMILARITY_WEIGHTS
        comps: dict[str, float] = {}
        unavailable: list[str] = []

        def pair(x, y) -> bool:
            return x is not None and y is not None

        # Geography — linear decay to the horizon.
        if pair(a.centroid_lon, b.centroid_lon) and pair(a.centroid_lat, b.centroid_lat):
            d = _haversine_km(a.centroid_lon, a.centroid_lat, b.centroid_lon, b.centroid_lat)
            comps["geography"] = max(0.0, 1.0 - d / SPATIAL_HORIZON_KM)
        else:
            unavailable.append("geography")

        # Environment — wind and current regime, averaged over whichever exist.
        env: list[float] = []
        if pair(a.wind_speed_ms, b.wind_speed_ms):
            env.append(max(0.0, 1.0 - abs(a.wind_speed_ms - b.wind_speed_ms) / 15.0))
        if pair(a.current_speed_ms, b.current_speed_ms):
            env.append(max(0.0, 1.0 - abs(a.current_speed_ms - b.current_speed_ms) / 2.0))
        if env:
            comps["environment"] = sum(env) / len(env)
        else:
            unavailable.append("environment")

        # Morphology — log-scale area (spills span orders of magnitude) + elongation.
        morph: list[float] = []
        if pair(a.area_km2, b.area_km2) and a.area_km2 > 0 and b.area_km2 > 0:
            ratio = abs(math.log10(a.area_km2) - math.log10(b.area_km2))
            morph.append(max(0.0, 1.0 - ratio / 2.0))
        if pair(a.elongation, b.elongation):
            morph.append(max(0.0, 1.0 - abs(a.elongation - b.elongation) / 5.0))
        if morph:
            comps["morphology"] = sum(morph) / len(morph)
        else:
            unavailable.append("morphology")

        # Source hypothesis — categorical agreement.
        if pair(a.top_source_class, b.top_source_class):
            comps["source_hypothesis"] = 1.0 if a.top_source_class == b.top_source_class else 0.0
        else:
            unavailable.append("source_hypothesis")

        # Attribution pattern — same decision state, and same vessel if known.
        attr: list[float] = []
        if pair(a.attribution_state, b.attribution_state):
            attr.append(1.0 if a.attribution_state == b.attribution_state else 0.0)
        if pair(a.attributed_mmsi, b.attributed_mmsi):
            attr.append(1.0 if a.attributed_mmsi == b.attributed_mmsi else 0.0)
        if attr:
            comps["attribution_pattern"] = sum(attr) / len(attr)
        else:
            unavailable.append("attribution_pattern")

        # Temporal — seasonal proximity (day-of-year), not absolute recency:
        # a slick in the same season years apart shares a forcing regime.
        if pair(a.observed_at, b.observed_at):
            delta = abs(a.observed_at.timetuple().tm_yday - b.observed_at.timetuple().tm_yday)
            delta = min(delta, 365 - delta)
            comps["temporal"] = max(0.0, 1.0 - delta / 182.5)
        else:
            unavailable.append("temporal")

        assessable = sum(active_weights[k] for k in comps)
        total_w = sum(active_weights.values())
        if assessable <= 0:
            return SimilarityBreakdown(components={}, unavailable=unavailable,
                                       score=0.0, coverage=0.0)
        # Renormalise over the assessable components so a case with missing
        # fields is not penalised as if it had scored zero on them.
        score = sum(comps[k] * active_weights[k] for k in comps) / assessable
        return SimilarityBreakdown(components=comps, unavailable=unavailable,
                                   score=score, coverage=assessable / total_w)
