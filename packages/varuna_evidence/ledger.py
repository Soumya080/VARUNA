"""
VARUNA GRID — Evidence Ledger.

The case's evolving evidence graph, in one place. Before this module, a
module that needed to know "what do we currently believe, and on what basis"
had to reconstruct it from `case.metadata`, stage results, and scattered
envelopes. The ledger makes that a first-class, queryable, auditable object.

Two design rules it enforces structurally:

1. **Revision never destroys.** `revise()` supersedes an item rather than
   mutating it; the prior version stays in the ledger, marked SUPERSEDED,
   pointing at its replacement. An audit that cannot see what was previously
   believed cannot explain why a decision was made at the time it was made.

2. **Contradiction is recorded, not resolved.** The ledger stores that two
   items disagree; it does not decide which one wins. That judgement belongs
   to NYAYA/the Validity Gate, which have the scientific contracts for it.
   A ledger that silently picked a winner would be making attribution
   decisions in a data structure.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode
from varuna_contracts.schemas import BBox


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceKind(StrEnum):
    """What kind of claim an item makes. Used for typed retrieval."""
    DETECTION = "detection"
    FORCING = "forcing"
    AIS = "ais"
    ORIGIN = "origin"                # PRATIVARTAN / Phi
    ATTRIBUTION = "attribution"      # NYAYA
    SOURCE_HYPOTHESIS = "source_hypothesis"   # CHHAYA
    FORECAST = "forecast"            # PRAVAAH
    VALIDITY = "validity"
    UNCERTAINTY = "uncertainty"
    DATA_QUALITY = "data_quality"
    MEMORY = "memory"                # SMRITI retrieval
    DECISION = "decision"
    OPERATOR = "operator"            # human input


class EvidenceStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"          # withdrawn; never silently deleted


class EvidenceItem(BaseModel):
    """One claim, with everything needed to audit it later."""
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    case_id: str
    kind: EvidenceKind
    produced_by: str                             # module/source that made the claim
    summary: str                                 # human-readable, one line
    observation: dict = Field(default_factory=dict)   # structured payload

    observed_at: datetime | None = None          # when the phenomenon occurred
    recorded_at: datetime = Field(default_factory=_utcnow)  # when we learned it
    time_window_hours: tuple[float, float] | None = None
    geometry: BBox | None = None

    confidence: float | None = Field(None, ge=0, le=1)
    uncertainty_note: str | None = None

    mode: EvidenceMode
    envelope: EvidenceEnvelope | None = None

    depends_on: list[str] = Field(default_factory=list)      # upstream evidence_ids
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)

    status: EvidenceStatus = EvidenceStatus.ACTIVE
    superseded_by: str | None = None
    revision: int = Field(0, ge=0)


class Contradiction(BaseModel):
    """A recorded disagreement. Deliberately carries no winner."""
    model_config = ConfigDict(extra="forbid")

    left_id: str
    right_id: str
    left_summary: str
    right_summary: str
    note: str | None = None


class EvidenceLedger:
    """
    Append-and-revise store for one or more cases' evidence.

    Not a database: an in-process structure the Case Engine owns for the life
    of a run, and which PRAMAN serialises for the permanent record. Storage
    lives behind PRAMAN/repositories, which already exist — duplicating a
    persistence layer here would be a second source of truth.
    """

    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}
        self._by_case: dict[str, list[str]] = defaultdict(list)

    # ------------------------------------------------------------- writing

    def append(
        self,
        *,
        case_id: str,
        kind: EvidenceKind,
        produced_by: str,
        summary: str,
        mode: EvidenceMode,
        observation: dict | None = None,
        envelope: EvidenceEnvelope | None = None,
        observed_at: datetime | None = None,
        time_window_hours: tuple[float, float] | None = None,
        geometry: BBox | None = None,
        confidence: float | None = None,
        uncertainty_note: str | None = None,
        depends_on: list[str] | None = None,
        evidence_id: str | None = None,
    ) -> EvidenceItem:
        """Record a new claim. Returns the stored item."""
        for dep in depends_on or []:
            if dep not in self._items:
                raise KeyError(
                    f"depends_on references unknown evidence_id {dep!r} — a "
                    "dependency edge into nothing makes the graph unauditable"
                )
        eid = evidence_id or f"ev-{kind.value}-{uuid.uuid4().hex[:8]}"
        if eid in self._items:
            raise ValueError(f"evidence_id {eid!r} already exists; use revise()")
        item = EvidenceItem(
            evidence_id=eid, case_id=case_id, kind=kind, produced_by=produced_by,
            summary=summary, observation=observation or {}, mode=mode,
            envelope=envelope, observed_at=observed_at,
            time_window_hours=time_window_hours, geometry=geometry,
            confidence=confidence, uncertainty_note=uncertainty_note,
            depends_on=list(depends_on or []),
        )
        self._items[eid] = item
        self._by_case[case_id].append(eid)
        return item

    def revise(self, evidence_id: str, *, summary: str | None = None,
               observation: dict | None = None, confidence: float | None = None,
               mode: EvidenceMode | None = None,
               uncertainty_note: str | None = None,
               produced_by: str | None = None) -> EvidenceItem:
        """
        Supersede an item with a new revision. The prior item is retained and
        marked SUPERSEDED — history is never rewritten in place.
        """
        prior = self._require(evidence_id)
        if prior.status is not EvidenceStatus.ACTIVE:
            raise ValueError(
                f"cannot revise {evidence_id!r}: status is {prior.status.value}, "
                "not active"
            )
        new_id = f"{prior.evidence_id}-r{prior.revision + 1}"
        replacement = prior.model_copy(update={
            "evidence_id": new_id,
            "summary": summary if summary is not None else prior.summary,
            "observation": observation if observation is not None else prior.observation,
            "confidence": confidence if confidence is not None else prior.confidence,
            "mode": mode if mode is not None else prior.mode,
            "uncertainty_note": (uncertainty_note if uncertainty_note is not None
                                 else prior.uncertainty_note),
            "produced_by": produced_by if produced_by is not None else prior.produced_by,
            "revision": prior.revision + 1,
            "recorded_at": _utcnow(),
            "status": EvidenceStatus.ACTIVE,
            "superseded_by": None,
            "depends_on": list(prior.depends_on) + [prior.evidence_id],
        })
        self._items[prior.evidence_id] = prior.model_copy(update={
            "status": EvidenceStatus.SUPERSEDED, "superseded_by": new_id,
        })
        self._items[new_id] = replacement
        self._by_case[prior.case_id].append(new_id)
        return replacement

    def retract(self, evidence_id: str, reason: str) -> EvidenceItem:
        """Withdraw a claim. Retained, never deleted."""
        prior = self._require(evidence_id)
        note = f"RETRACTED: {reason}"
        updated = prior.model_copy(update={
            "status": EvidenceStatus.RETRACTED,
            "uncertainty_note": (f"{prior.uncertainty_note} | {note}"
                                 if prior.uncertainty_note else note),
        })
        self._items[evidence_id] = updated
        return updated

    def link_support(self, evidence_id: str, supports_id: str) -> None:
        self._relate(evidence_id, supports_id, "supports")

    def link_contradiction(self, evidence_id: str, contradicts_id: str,
                           note: str | None = None) -> None:
        """
        Record that two items disagree. Symmetric: a contradiction that only
        one side knows about is invisible from the other side's audit trail.
        """
        self._relate(evidence_id, contradicts_id, "contradicts")
        self._relate(contradicts_id, evidence_id, "contradicts")
        if note:
            left = self._items[evidence_id]
            merged = f"{left.uncertainty_note} | {note}" if left.uncertainty_note else note
            self._items[evidence_id] = left.model_copy(update={"uncertainty_note": merged})

    # ------------------------------------------------------------- reading

    def get(self, evidence_id: str) -> EvidenceItem | None:
        return self._items.get(evidence_id)

    def for_case(self, case_id: str, *, include_inactive: bool = False) -> list[EvidenceItem]:
        items = [self._items[i] for i in self._by_case.get(case_id, [])]
        if include_inactive:
            return items
        return [i for i in items if i.status is EvidenceStatus.ACTIVE]

    def by_kind(self, case_id: str, kind: EvidenceKind, *,
                include_inactive: bool = False) -> list[EvidenceItem]:
        return [i for i in self.for_case(case_id, include_inactive=include_inactive)
                if i.kind is kind]

    def latest(self, case_id: str, kind: EvidenceKind) -> EvidenceItem | None:
        """
        Most recently recorded ACTIVE item of a kind, or None.

        Ties on `recorded_at` are broken by INSERTION ORDER, not left to
        `max()`. Two items appended in the same microsecond -- routine, since
        several are written back-to-back in one pass -- otherwise resolved to
        whichever `max()` happened to see first, which is the EARLIER one.
        That made "latest" silently return a stale item.
        """
        items = self.by_kind(case_id, kind)
        if not items:
            return None
        # `by_kind` preserves append order, so the last item with the maximal
        # timestamp is the genuinely most recent one.
        newest = max(i.recorded_at for i in items)
        return [i for i in items if i.recorded_at == newest][-1]

    def contradictions(self, case_id: str) -> list[Contradiction]:
        """Every recorded disagreement, de-duplicated across the symmetric pair."""
        seen: set[tuple[str, str]] = set()
        out: list[Contradiction] = []
        for item in self.for_case(case_id):
            for other_id in item.contradicts:
                other = self._items.get(other_id)
                if other is None or other.status is not EvidenceStatus.ACTIVE:
                    continue
                key = tuple(sorted((item.evidence_id, other_id)))
                if key in seen:
                    continue
                seen.add(key)
                out.append(Contradiction(
                    left_id=key[0], right_id=key[1],
                    left_summary=self._items[key[0]].summary,
                    right_summary=self._items[key[1]].summary,
                    note=item.uncertainty_note,
                ))
        return out

    def worst_mode(self, case_id: str) -> EvidenceMode | None:
        """
        The weakest evidence mode among active items — the case's honest
        overall mode, by the same monotonic-worsening rule as EvidenceEnvelope.
        """
        items = self.for_case(case_id)
        if not items:
            return None
        return max((i.mode for i in items), key=lambda m: m.rank)

    def lineage(self, evidence_id: str) -> list[EvidenceItem]:
        """This item and everything it transitively depends on, nearest first."""
        out: list[EvidenceItem] = []
        seen: set[str] = set()
        stack = [evidence_id]
        while stack:
            eid = stack.pop(0)
            if eid in seen:
                continue
            seen.add(eid)
            item = self._items.get(eid)
            if item is None:
                continue
            out.append(item)
            stack.extend(item.depends_on)
        return out

    def audit_trail(self, case_id: str) -> list[dict]:
        """Flat, chronological, JSON-ready record for PRAMAN."""
        items = sorted(self.for_case(case_id, include_inactive=True),
                       key=lambda i: i.recorded_at)
        return [{
            "evidence_id": i.evidence_id, "kind": i.kind.value,
            "produced_by": i.produced_by, "summary": i.summary,
            "mode": i.mode.value, "status": i.status.value,
            "confidence": i.confidence, "revision": i.revision,
            "recorded_at": i.recorded_at.isoformat(),
            "depends_on": i.depends_on, "contradicts": i.contradicts,
            "superseded_by": i.superseded_by,
        } for i in items]

    # ------------------------------------------------------------ internals

    def _require(self, evidence_id: str) -> EvidenceItem:
        item = self._items.get(evidence_id)
        if item is None:
            raise KeyError(f"unknown evidence_id {evidence_id!r}")
        return item

    def _relate(self, evidence_id: str, other_id: str, field: str) -> None:
        item = self._require(evidence_id)
        self._require(other_id)
        current: list[str] = list(getattr(item, field))
        if other_id not in current:
            current.append(other_id)
            self._items[evidence_id] = item.model_copy(update={field: current})
