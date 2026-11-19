"""
SMRITI adaptive reweighting from operator feedback (Phase 7).

WHAT THIS IS
------------
A lightweight, fully deterministic, fully auditable credit-assignment
mechanism — NOT a training loop, NOT gradient descent, NOT a hidden model.
An operator judges whether a SMRITI hit was actually a useful precedent
(`useful: bool`); this module nudges `SIMILARITY_WEIGHTS` toward whichever
similarity components tend to be high when a hit turns out useful, and away
from components that are high when a hit turns out irrelevant.

The update rule, per component `k`:

    credit[k] += (+1 if useful else -1) * components_at_retrieval[k]
    count[k]  += 1
    adjusted_weight[k] = base_weight[k] * clamp(1 + LEARNING_RATE * credit[k]/count[k], 0.5, 1.5)

then renormalised to sum to 1, matching `SIMILARITY_WEIGHTS`'s own
invariant. O(1) per feedback event. Fully recomputable from the feedback log
at any time — there is no hidden model state beyond that log, so the
"model" can always be reconstructed, inspected, or rolled back by deleting
feedback rows.

WHAT THIS IS NOT
----------------
- Not deep learning, not a bandit *policy* in the RL sense — it is honestly
  a contextual credit-assignment / reweighting scheme. "Bandit-flavoured,"
  not "a bandit."
- Not a replacement for `SIMILARITY_WEIGHTS` — that stays the declared,
  auditable default/fallback (see memory.py's own "declared, not fitted"
  framing). Adaptive weights are always explicitly labelled `weights_source
  ="adaptive"` on any result that used them; nothing here silently changes
  what an existing caller gets (see `memory.py::retrieve_similar_cases`'s
  `weights=None` default).
- Does not touch `SmritiStore`/`CaseMemory`/`MemoryRetrieval` — kept in a
  separate module deliberately, so the already-tested `memory.py` is never
  at risk from this addition.
"""
from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from varuna_smriti.memory import SIMILARITY_WEIGHTS

LEARNING_RATE = 0.5
_MIN_MULTIPLIER = 0.5
_MAX_MULTIPLIER = 1.5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryFeedback(BaseModel):
    """One operator judgment on whether a retrieved similar case was a
    genuinely useful precedent."""
    model_config = ConfigDict(extra="forbid")

    feedback_id: str = Field(default_factory=lambda: f"fb-{uuid.uuid4().hex[:10]}")
    query_case_id: str
    retrieved_case_id: str
    similarity_at_retrieval: float
    # Captured verbatim from the SimilarityBreakdown.components the
    # retrieval actually produced — never recomputed at feedback time,
    # which could silently drift if the underlying cases changed.
    components_at_retrieval: dict[str, float] = Field(default_factory=dict)
    useful: bool
    recorded_at: datetime = Field(default_factory=_utcnow)
    recorded_by: str

    def to_line(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True)


class SmritiFeedbackStore:
    """JSON-lines append log — same atomic-write discipline as
    `SmritiStore._flush()`, kept as a separate file
    (`smriti_feedback.jsonl`) rather than touching `SmritiStore`'s own
    storage."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._items: list[MemoryFeedback] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                self._items.append(MemoryFeedback.model_validate_json(raw))
            except Exception:
                # A corrupt line must not take down every future feedback
                # submission — skip it, the line stays on disk for inspection.
                continue

    def record(self, feedback: MemoryFeedback) -> MemoryFeedback:
        self._items.append(feedback)
        self._flush()
        return feedback

    def all(self) -> list[MemoryFeedback]:
        return list(self._items)

    def _flush(self) -> None:
        tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False,
                dir=str(self._path.parent), suffix=".tmp",
            ) as fh:
                tmp = Path(fh.name)
                for item in self._items:
                    fh.write(item.to_line() + "\n")
            tmp.replace(self._path)
            tmp = None
        finally:
            if tmp is not None and tmp.exists():
                tmp.unlink()


def compute_adaptive_weights(
    feedback: list[MemoryFeedback],
    *, base_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Pure function: base weights + a feedback log -> adjusted weights.
    Recomputable at any time from the log alone — no persisted "model"
    beyond the feedback rows themselves.

    Renormalised to sum to 1, matching `SIMILARITY_WEIGHTS`'s own invariant.
    With an empty feedback log, returns the base weights unchanged (byte-
    for-byte, so a caller with zero feedback history sees no behavior
    change from opting into "adaptive" mode).
    """
    base = dict(base_weights) if base_weights is not None else dict(SIMILARITY_WEIGHTS)
    if not feedback:
        return base

    credit: dict[str, float] = {k: 0.0 for k in base}
    count: dict[str, int] = {k: 0 for k in base}
    for fb in feedback:
        sign = 1.0 if fb.useful else -1.0
        for k, v in fb.components_at_retrieval.items():
            if k not in credit:
                continue  # ignore components from a since-retired similarity axis
            credit[k] += sign * v
            count[k] += 1

    adjusted: dict[str, float] = {}
    for k, base_w in base.items():
        if count[k] == 0:
            adjusted[k] = base_w
            continue
        avg_credit = credit[k] / count[k]
        multiplier = max(_MIN_MULTIPLIER, min(_MAX_MULTIPLIER, 1.0 + LEARNING_RATE * avg_credit))
        adjusted[k] = base_w * multiplier

    total = sum(adjusted.values())
    if total <= 0:
        return base  # pathological case guard; never divide by zero or return negatives
    return {k: v / total for k, v in adjusted.items()}
