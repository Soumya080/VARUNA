"""
Agentic orchestration loop — action selection, termination, and fail-closed
behaviour.

The property that matters most here is the last one: the loop must never
reach PROCEED_TO_DECISION on evidence it did not actually obtain.
"""
from __future__ import annotations

import pytest

from varuna_agentic import ActionSelector, AgenticLoop, UncertaintyAssessor
from varuna_contracts.action import (
    ActionKind, ActionOutcome, ActionRecord, LoopPhase,
)
from varuna_contracts.detection_evidence import OODRisk
from varuna_contracts.evidence import EvidenceMode
from varuna_evidence import EvidenceKind, EvidenceLedger

pytestmark = pytest.mark.unit

# Which evidence kind a successfully-executed action produces.
_PRODUCES = {
    ActionKind.INSPECT_DETECTION_QUALITY: EvidenceKind.DATA_QUALITY,
    ActionKind.RUN_RECONSTRUCTION: EvidenceKind.ORIGIN,
    ActionKind.EXPAND_AIS_SEARCH: EvidenceKind.AIS,
    ActionKind.RUN_SOURCE_HYPOTHESIS: EvidenceKind.SOURCE_HYPOTHESIS,
    ActionKind.CONSULT_MEMORY: EvidenceKind.MEMORY,
}


def _cooperative_executor(action, ledger):
    """An executor whose actions all succeed."""
    kind = _PRODUCES.get(action.kind)
    if kind is None:
        return ActionRecord(action=action, outcome=ActionOutcome.NO_CHANGE,
                            result_summary="nothing to do for this action kind",
                            changed=False)
    item = ledger.append(
        case_id=action.case_id, kind=kind, produced_by="test-executor",
        summary=f"{kind.value} produced", mode=EvidenceMode.REAL, confidence=0.85,
    )
    return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                        result_summary=f"added {kind.value}",
                        evidence_added=[item.evidence_id], changed=True)


def _healthy_ledger(case_id="C") -> EvidenceLedger:
    led = EvidenceLedger()
    led.append(case_id=case_id, kind=EvidenceKind.DETECTION, produced_by="netra",
               summary="slick detected", mode=EvidenceMode.REAL, confidence=0.92,
               observation={"ood_risk": "in_domain"})
    return led


# ------------------------------------------------------------ happy path

def test_healthy_case_gathers_evidence_then_proceeds():
    led = _healthy_ledger()
    trace, _ = AgenticLoop().run("C", led, executor=_cooperative_executor)
    assert trace.terminal_action is ActionKind.PROCEED_TO_DECISION
    kinds = {i.kind for i in led.for_case("C")}
    assert {EvidenceKind.DATA_QUALITY, EvidenceKind.ORIGIN, EvidenceKind.AIS,
            EvidenceKind.SOURCE_HYPOTHESIS, EvidenceKind.MEMORY} <= kinds


def test_every_action_names_the_uncertainty_that_motivated_it():
    led = _healthy_ledger()
    trace, _ = AgenticLoop().run("C", led, executor=_cooperative_executor)
    actions = [s.action for s in trace.steps if s.action is not None]
    assert actions
    for a in actions:
        assert a.because.strip(), f"{a.kind} has no justification"
        assert a.targets_uncertainty
        assert a.expected_effect


def test_trace_renders_a_readable_explanation():
    led = _healthy_ledger()
    trace, _ = AgenticLoop().run("C", led, executor=_cooperative_executor)
    text = trace.render()
    assert "Decision trace for case C" in text
    assert "TERMINAL" in text


# --------------------------------------------------------- fail-closed core

def test_loop_does_not_proceed_when_every_action_fails():
    """
    THE fail-closed property. "All actions attempted" is not "all evidence
    gathered": if the executor never succeeded, the case must not advance to
    a decision on evidence that was never obtained.
    """
    led = _healthy_ledger()

    def failing(action, ledger):
        raise RuntimeError("executor unavailable")

    trace, _ = AgenticLoop().run("C", led, executor=failing)
    assert trace.terminal_action is ActionKind.STOP_INSUFFICIENT_EVIDENCE
    assert "could not be obtained" in trace.terminal_reason


def test_loop_does_not_proceed_without_an_executor():
    trace, _ = AgenticLoop().run("C", _healthy_ledger())
    assert trace.terminal_action is ActionKind.STOP_INSUFFICIENT_EVIDENCE


def test_executor_exception_is_recorded_not_propagated():
    led = _healthy_ledger()

    def failing(action, ledger):
        raise RuntimeError("boom")

    trace, _ = AgenticLoop().run("C", led, executor=failing)   # must not raise
    records = [s.record for s in trace.steps if s.record is not None]
    failed = [r for r in records if r.outcome is ActionOutcome.FAILED]
    assert failed
    assert "boom" in failed[0].error


def test_no_detection_stops_rather_than_reasoning_on_nothing():
    trace, _ = AgenticLoop().run("EMPTY", EvidenceLedger(),
                                 executor=_cooperative_executor)
    assert trace.terminal_action is ActionKind.STOP_INSUFFICIENT_EVIDENCE


def test_out_of_domain_detection_never_reaches_a_decision():
    """
    An OOD detection's confidence cannot carry a decision alone. This is the
    MC20 situation in miniature and must not silently proceed.
    """
    led = EvidenceLedger()
    led.append(case_id="OOD", kind=EvidenceKind.DETECTION, produced_by="netra",
               summary="weak activation", mode=EvidenceMode.REAL, confidence=0.3,
               observation={"ood_risk": "out_of_domain"})
    led.append(case_id="OOD", kind=EvidenceKind.DATA_QUALITY, produced_by="guard",
               summary="input accepted", mode=EvidenceMode.REAL, confidence=0.9)
    trace, unc = AgenticLoop().run("OOD", led, executor=_cooperative_executor)
    assert trace.terminal_action is not ActionKind.PROCEED_TO_DECISION
    assert unc.ood_risk is OODRisk.OUT_OF_DOMAIN
    assert unc.dominant_concern == "ood_risk"


def test_contradictions_are_addressed_before_any_decision():
    led = _healthy_ledger("X")
    det = led.latest("X", EvidenceKind.DETECTION)
    ais = led.append(case_id="X", kind=EvidenceKind.AIS, produced_by="ais",
                     summary="no vessel within 50 km", mode=EvidenceMode.REAL)
    led.link_contradiction(det.evidence_id, ais.evidence_id)
    led.append(case_id="X", kind=EvidenceKind.DATA_QUALITY, produced_by="guard",
               summary="ok", mode=EvidenceMode.REAL, confidence=0.9)

    selected = ActionSelector().select(
        "X", led, UncertaintyAssessor().assess("X", led), attempted=set())
    assert selected.kind is ActionKind.RESOLVE_CONTRADICTION


# ------------------------------------------------------------- termination

def test_loop_always_terminates_within_its_budget():
    led = _healthy_ledger()

    def no_op(action, ledger):
        return ActionRecord(action=action, outcome=ActionOutcome.NO_CHANGE,
                            result_summary="did nothing", changed=False)

    loop = AgenticLoop(max_iterations=5)
    trace, _ = loop.run("C", led, executor=no_op)
    assert trace.iterations <= 5
    assert trace.terminal_action is not None


def test_budget_exhaustion_is_reported_as_insufficient_not_success():
    """Running out of iterations is not a decision. It must never look like one."""
    led = _healthy_ledger()
    calls = {"n": 0}

    def churner(action, ledger):
        # Always "succeeds" but never produces the evidence the selector needs,
        # so the loop keeps finding work to do.
        calls["n"] += 1
        ledger.append(case_id=action.case_id, kind=EvidenceKind.OPERATOR,
                      produced_by="noise", summary=f"note {calls['n']}",
                      mode=EvidenceMode.REAL)
        return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                            result_summary="noise", changed=True)

    trace, _ = AgenticLoop(max_iterations=2).run("C", led, executor=churner)
    if trace.halted_on_budget:
        assert trace.terminal_action is ActionKind.STOP_INSUFFICIENT_EVIDENCE
        assert "budget" in trace.terminal_reason


def test_an_action_is_never_selected_twice_for_the_same_case():
    led = _healthy_ledger()

    def no_op(action, ledger):
        return ActionRecord(action=action, outcome=ActionOutcome.NO_CHANGE,
                            result_summary="no", changed=False)

    trace, _ = AgenticLoop().run("C", led, executor=no_op)
    # Count SELECT_ACTION steps only: each action also appears on its EXECUTE
    # step, so scanning every step would double-count by construction.
    selected = [s.action.kind for s in trace.steps
                if s.phase is LoopPhase.SELECT_ACTION
                and s.action is not None and not s.action.kind.is_terminal]
    assert selected, "expected at least one non-terminal action"
    assert len(selected) == len(set(selected)), f"an action repeated: {selected}"


# ------------------------------------------------------------- uncertainty

def test_absent_components_are_none_not_a_fabricated_midpoint():
    unc = UncertaintyAssessor().assess("NOTHING", EvidenceLedger())
    assert unc.model_confidence is None
    assert unc.data_quality is None
    assert unc.ood_risk is OODRisk.UNKNOWN
    assert unc.dominant_concern == "insufficient_assessment"
    assert "model_confidence" in unc.component_notes


def test_conflicts_are_counted_and_lower_agreement():
    led = _healthy_ledger("Y")
    det = led.latest("Y", EvidenceKind.DETECTION)
    other = led.append(case_id="Y", kind=EvidenceKind.AIS, produced_by="ais",
                       summary="contradicts", mode=EvidenceMode.REAL)
    led.link_contradiction(det.evidence_id, other.evidence_id)
    unc = UncertaintyAssessor().assess("Y", led)
    assert unc.evidence_conflict_count == 1
    assert unc.evidence_agreement.value < 1.0
    assert unc.dominant_concern == "evidence_conflict"


def test_unrecognised_ood_value_degrades_to_unknown_not_a_crash():
    led = EvidenceLedger()
    led.append(case_id="Z", kind=EvidenceKind.DETECTION, produced_by="netra",
               summary="d", mode=EvidenceMode.REAL, confidence=0.5,
               observation={"ood_risk": "banana"})
    unc = UncertaintyAssessor().assess("Z", led)
    assert unc.ood_risk is OODRisk.UNKNOWN
    assert "banana" in unc.component_notes["ood_risk"]
