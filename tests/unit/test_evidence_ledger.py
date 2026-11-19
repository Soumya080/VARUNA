"""Evidence Ledger — append/revise/contradiction/lineage/audit invariants."""
from __future__ import annotations

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_evidence import EvidenceKind, EvidenceLedger, EvidenceStatus

pytestmark = pytest.mark.unit


def _ledger_with_detection(case_id: str = "C1"):
    led = EvidenceLedger()
    item = led.append(
        case_id=case_id, kind=EvidenceKind.DETECTION, produced_by="netra",
        summary="slick candidate", mode=EvidenceMode.REAL, confidence=0.9,
    )
    return led, item


def test_append_returns_a_retrievable_item():
    led, item = _ledger_with_detection()
    assert led.get(item.evidence_id) is item or led.get(item.evidence_id) == item
    assert led.for_case("C1") == [item]


def test_dependency_on_unknown_evidence_is_rejected():
    """A dependency edge pointing at nothing makes the graph unauditable."""
    led = EvidenceLedger()
    with pytest.raises(KeyError, match="unknown evidence_id"):
        led.append(case_id="C1", kind=EvidenceKind.AIS, produced_by="ais",
                   summary="x", mode=EvidenceMode.REAL, depends_on=["ghost"])


def test_revision_supersedes_without_destroying_history():
    led, item = _ledger_with_detection()
    revised = led.revise(item.evidence_id, summary="refined", confidence=0.6)

    prior = led.get(item.evidence_id)
    assert prior.status is EvidenceStatus.SUPERSEDED
    assert prior.superseded_by == revised.evidence_id
    assert prior.summary == "slick candidate"      # original text intact
    assert prior.confidence == 0.9                 # original value intact

    assert revised.revision == 1
    assert item.evidence_id in revised.depends_on  # lineage back to the original
    assert led.for_case("C1") == [revised]         # only the revision is active


def test_revising_a_superseded_item_is_refused():
    led, item = _ledger_with_detection()
    led.revise(item.evidence_id, summary="v2")
    with pytest.raises(ValueError, match="not active"):
        led.revise(item.evidence_id, summary="v3")


def test_retract_retains_the_item_and_records_the_reason():
    led, item = _ledger_with_detection()
    out = led.retract(item.evidence_id, "operator withdrew the report")
    assert out.status is EvidenceStatus.RETRACTED
    assert "operator withdrew" in out.uncertainty_note
    assert led.get(item.evidence_id) is not None            # never deleted
    assert led.for_case("C1") == []                          # but not active
    assert len(led.for_case("C1", include_inactive=True)) == 1


def test_contradiction_is_symmetric_and_deduplicated():
    led, det = _ledger_with_detection()
    ais = led.append(case_id="C1", kind=EvidenceKind.AIS, produced_by="ais",
                     summary="no vessel within 50 km", mode=EvidenceMode.REAL)
    led.link_contradiction(det.evidence_id, ais.evidence_id, note="det without vessel")

    assert ais.evidence_id in led.get(det.evidence_id).contradicts
    assert det.evidence_id in led.get(ais.evidence_id).contradicts   # symmetric
    pairs = led.contradictions("C1")
    assert len(pairs) == 1                                            # not double-counted


def test_ledger_records_contradiction_but_does_not_resolve_it():
    """
    Deciding which of two conflicting claims wins is NYAYA's/the gate's job.
    The ledger must not expose anything that picks a winner.
    """
    led, det = _ledger_with_detection()
    ais = led.append(case_id="C1", kind=EvidenceKind.AIS, produced_by="ais",
                     summary="no vessel", mode=EvidenceMode.REAL)
    led.link_contradiction(det.evidence_id, ais.evidence_id)
    contradiction = led.contradictions("C1")[0]
    for banned in ("winner", "resolved", "correct", "preferred"):
        assert not hasattr(contradiction, banned)
    # both sides remain equally active
    assert {i.evidence_id for i in led.for_case("C1")} == {det.evidence_id, ais.evidence_id}


def test_worst_mode_follows_monotonic_worsening():
    led, _ = _ledger_with_detection()
    assert led.worst_mode("C1") is EvidenceMode.REAL
    led.append(case_id="C1", kind=EvidenceKind.FORECAST, produced_by="pravaah",
               summary="drift", mode=EvidenceMode.SIMULATED)
    assert led.worst_mode("C1") is EvidenceMode.SIMULATED
    led.append(case_id="C1", kind=EvidenceKind.AIS, produced_by="ais",
               summary="nothing", mode=EvidenceMode.UNAVAILABLE)
    assert led.worst_mode("C1") is EvidenceMode.UNAVAILABLE
    # ...and never improves just because something REAL arrives afterwards
    led.append(case_id="C1", kind=EvidenceKind.ORIGIN, produced_by="prativartan",
               summary="phi", mode=EvidenceMode.REAL)
    assert led.worst_mode("C1") is EvidenceMode.UNAVAILABLE


def test_worst_mode_of_empty_case_is_none_not_real():
    """An empty case has no evidence mode; defaulting to REAL would be a lie."""
    assert EvidenceLedger().worst_mode("nothing-here") is None


def test_lineage_walks_transitive_dependencies():
    led = EvidenceLedger()
    a = led.append(case_id="C1", kind=EvidenceKind.FORCING, produced_by="era5",
                   summary="forcing", mode=EvidenceMode.REAL)
    b = led.append(case_id="C1", kind=EvidenceKind.ORIGIN, produced_by="prativartan",
                   summary="phi", mode=EvidenceMode.REAL, depends_on=[a.evidence_id])
    c = led.append(case_id="C1", kind=EvidenceKind.ATTRIBUTION, produced_by="nyaya",
                   summary="attr", mode=EvidenceMode.REAL, depends_on=[b.evidence_id])
    chain = [i.evidence_id for i in led.lineage(c.evidence_id)]
    assert chain == [c.evidence_id, b.evidence_id, a.evidence_id]


def test_audit_trail_includes_superseded_items_in_time_order():
    led, item = _ledger_with_detection()
    led.revise(item.evidence_id, summary="refined")
    trail = led.audit_trail("C1")
    assert len(trail) == 2
    assert [r["status"] for r in trail] == ["superseded", "active"]
    assert trail[0]["superseded_by"] == trail[1]["evidence_id"]


def test_by_kind_and_latest_ignore_inactive_by_default():
    led, item = _ledger_with_detection()
    led.retract(item.evidence_id, "withdrawn")
    assert led.by_kind("C1", EvidenceKind.DETECTION) == []
    assert led.latest("C1", EvidenceKind.DETECTION) is None
    assert len(led.by_kind("C1", EvidenceKind.DETECTION, include_inactive=True)) == 1


def test_cases_are_isolated_from_each_other():
    led, _ = _ledger_with_detection("C1")
    led.append(case_id="C2", kind=EvidenceKind.DETECTION, produced_by="netra",
               summary="other case", mode=EvidenceMode.SIMULATED)
    assert len(led.for_case("C1")) == 1
    assert len(led.for_case("C2")) == 1
    assert led.worst_mode("C1") is EvidenceMode.REAL
    assert led.worst_mode("C2") is EvidenceMode.SIMULATED
