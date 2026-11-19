"""
VARUNA GRID — agentic orchestration loop.

    OBSERVE -> ASSESS -> IDENTIFY UNCERTAINTY -> SELECT NEXT BEST ACTION
    -> EXECUTE -> UPDATE EVIDENCE -> REASSESS -> ACT or STOP

WHAT THIS IS
------------
A deterministic, inspectable controller. It reads the Evidence Ledger, works
out what is missing/weak/contradictory, and picks the single highest-priority
action that would most reduce that specific uncertainty. Every decision is
recorded in a `DecisionTrace` naming the uncertainty that caused it.

NO LLM IS INVOLVED. There is no model call anywhere in this module. If one is
ever added, the boundary is fixed by design and stated here: an LLM may
propose or explain actions, but the authority for physical calculations,
validity verdicts, scientific measurements, mission authorization, and
forecast values stays with the modules that own those contracts. The action
*selection* below is a priority-ordered rule set precisely so that it is
reviewable and reproducible under replay.

TERMINATION
-----------
The loop is guaranteed to terminate: every action either adds evidence
(changing state) or is recorded as attempted, and an action already attempted
is never selected again for the same case. With a finite `ActionKind` set and
a hard iteration budget, it cannot spin.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from varuna_contracts.action import (
    ActionKind, ActionOutcome, ActionRecord, DecisionStep, DecisionTrace,
    LoopPhase, NextBestAction,
)
from varuna_contracts.detection_evidence import (
    MeasurementStatus, Measured, OODRisk, UncertaintyAssessment,
)
from varuna_evidence.ledger import EvidenceKind, EvidenceLedger

DEFAULT_MAX_ITERATIONS = 8

# An executor takes the selected action and the ledger, and returns a record.
Executor = Callable[[NextBestAction, EvidenceLedger], ActionRecord]


class UncertaintyAssessor:
    """
    Builds an `UncertaintyAssessment` from what the ledger actually contains.

    Absence is represented as absence: a component with no supporting evidence
    is left `None` (or UNKNOWN) rather than defaulted to a neutral 0.5, because
    a fabricated mid-range score is indistinguishable from a real one
    downstream.
    """

    def assess(self, case_id: str, ledger: EvidenceLedger) -> UncertaintyAssessment:
        detection = ledger.latest(case_id, EvidenceKind.DETECTION)
        quality = ledger.latest(case_id, EvidenceKind.DATA_QUALITY)
        attribution = ledger.latest(case_id, EvidenceKind.ATTRIBUTION)
        forecast = ledger.latest(case_id, EvidenceKind.FORECAST)
        contradictions = ledger.contradictions(case_id)

        notes: dict[str, str] = {}

        model_confidence = None
        if detection is not None and detection.confidence is not None:
            model_confidence = Measured(value=detection.confidence,
                                        status=MeasurementStatus.MEASURED)
        else:
            notes["model_confidence"] = "No detection evidence carrying a confidence."

        data_quality = None
        if quality is not None and quality.confidence is not None:
            data_quality = Measured(value=quality.confidence,
                                    status=MeasurementStatus.MEASURED)
        else:
            notes["data_quality"] = "Data guard has not reported for this case."

        # OOD may be recorded on the detection item, or -- when perception
        # produced nothing to annotate -- as standalone data-quality evidence.
        # Reading only the first source made UncertaintyAssessment report
        # UNKNOWN on exactly the cases where an OOD judgement HAD been made
        # and recorded elsewhere, so two components described the same fact
        # differently.
        # Scan ALL data-quality items, not just the most recent one: the OOD
        # judgement and the data-guard verdict are separate DATA_QUALITY
        # records, and the guard one is usually written later. Reading only
        # `latest` therefore found the guard record (which carries no
        # ood_risk) and reported UNKNOWN even though an OOD judgement had been
        # made and recorded -- leaving UncertaintyAssessment contradicting
        # DetectionEvidenceEnvelope about the same case.
        ood = OODRisk.UNKNOWN
        holders = [detection] + ledger.by_kind(case_id, EvidenceKind.DATA_QUALITY)
        for holder in holders:
            if holder is None:
                continue
            raw = holder.observation.get("ood_risk")
            if raw is None:
                continue
            try:
                ood = OODRisk(raw)
                break
            except ValueError:
                notes["ood_risk"] = f"Unrecognised ood_risk value {raw!r}; treated as UNKNOWN."

        attribution_uncertainty = None
        if attribution is not None:
            ent = attribution.observation.get("posterior_entropy")
            if isinstance(ent, (int, float)):
                attribution_uncertainty = Measured(value=float(ent),
                                                   status=MeasurementStatus.MEASURED)
        else:
            notes["attribution_uncertainty"] = "NYAYA has not produced an attribution."

        forecast_uncertainty = None
        if forecast is None:
            notes["forecast_uncertainty"] = "No forecast evidence exists."

        active = ledger.for_case(case_id)
        agreement = None
        if active:
            agreement = Measured(
                value=max(0.0, 1.0 - len(contradictions) / max(1, len(active))),
                status=MeasurementStatus.INFERRED,
                note="1 - (contradicting pairs / active evidence items).",
            )

        return UncertaintyAssessment(
            case_id=case_id,
            model_confidence=model_confidence,
            data_quality=data_quality,
            ood_risk=ood,
            evidence_agreement=agreement,
            evidence_conflict_count=len(contradictions),
            attribution_uncertainty=attribution_uncertainty,
            forecast_uncertainty=forecast_uncertainty,
            component_notes=notes,
        )


class ActionSelector:
    """
    Priority-ordered rule set. Returns the single most valuable next action, or
    a terminal action when nothing further would help.

    Order matters and encodes the product's safety posture: establish whether
    the perception input is trustworthy *before* reasoning on top of it, and
    resolve contradictions before proceeding to a decision.
    """

    def select(self, case_id: str, ledger: EvidenceLedger,
               unc: UncertaintyAssessment, attempted: set[ActionKind]) -> NextBestAction:
        def make(kind: ActionKind, because: str, targets: str, expected: str,
                 priority: int, required: list[str] | None = None) -> NextBestAction:
            return NextBestAction(
                action_id=f"act-{uuid.uuid4().hex[:8]}", case_id=case_id, kind=kind,
                because=because, targets_uncertainty=targets,
                required_evidence=required or [], expected_effect=expected,
                priority=priority,
            )

        detection = ledger.latest(case_id, EvidenceKind.DETECTION)

        # 0. No detection at all -> nothing downstream is meaningful.
        if detection is None:
            if ActionKind.INSPECT_DETECTION_QUALITY not in attempted:
                return make(ActionKind.INSPECT_DETECTION_QUALITY,
                            "No detection evidence is present for this case.",
                            "model_confidence",
                            "Establish whether perception ran and what it found.", 0)
            return make(ActionKind.STOP_INSUFFICIENT_EVIDENCE,
                        "Perception produced no detection, and re-inspection did not "
                        "change that. There is nothing to attribute or forecast.",
                        "model_confidence",
                        "Case ends in an honest no-detection state.", 0)

        # 1. Data quality unknown -> the input may not be trustworthy.
        if unc.data_quality is None and ActionKind.INSPECT_DETECTION_QUALITY not in attempted:
            return make(ActionKind.INSPECT_DETECTION_QUALITY,
                        "No data-quality assessment exists, so the trustworthiness of "
                        "the perception input is unknown.",
                        "data_quality",
                        "Data guard verdict recorded; input trustworthiness known.", 1)

        # 2. OOD unknown -> the model may be operating outside its domain.
        if unc.ood_risk is OODRisk.UNKNOWN and ActionKind.ASSESS_OOD not in attempted:
            return make(ActionKind.ASSESS_OOD,
                        "OOD risk has not been assessed; the detector may be operating "
                        "outside its training domain.",
                        "ood_risk", "OOD risk classified; confidence contextualised.", 1)

        # 3. OOD high -> do not build a decision on it; get more evidence.
        if unc.ood_risk is OODRisk.OUT_OF_DOMAIN:
            if ActionKind.REQUEST_ADDITIONAL_EVIDENCE not in attempted:
                return make(ActionKind.REQUEST_ADDITIONAL_EVIDENCE,
                            "Detection is out-of-domain, so its confidence cannot carry a "
                            "decision on its own; independent corroboration is required.",
                            "ood_risk",
                            "Either corroborating evidence arrives, or the case ends "
                            "restricted rather than falsely confident.", 0)
            return make(ActionKind.STOP_INSUFFICIENT_EVIDENCE,
                        "Detection is out-of-domain and no corroborating evidence was "
                        "obtainable. Proceeding would assert a conclusion the evidence "
                        "does not support.",
                        "ood_risk", "Case ends restricted/inconclusive, safely.", 0)

        # 4. Contradictions -> resolve before deciding.
        if unc.evidence_conflict_count > 0 and ActionKind.RESOLVE_CONTRADICTION not in attempted:
            pairs = ledger.contradictions(case_id)
            detail = "; ".join(f"{c.left_summary} <> {c.right_summary}" for c in pairs[:2])
            return make(ActionKind.RESOLVE_CONTRADICTION,
                        f"{unc.evidence_conflict_count} unresolved contradiction(s): {detail}",
                        "evidence_conflict",
                        "Contradiction examined and either reconciled or explicitly "
                        "carried as a caveat.", 0)

        # 5. No origin reconstruction yet.
        if (ledger.latest(case_id, EvidenceKind.ORIGIN) is None
                and ActionKind.RUN_RECONSTRUCTION not in attempted):
            return make(ActionKind.RUN_RECONSTRUCTION,
                        "No origin reconstruction exists; where the slick came from is "
                        "unknown.", "attribution_uncertainty",
                        "Phi field produced, enabling origin-based attribution.", 2,
                        required=["forcing", "detection"])

        # 6. No AIS evidence yet.
        if (ledger.latest(case_id, EvidenceKind.AIS) is None
                and ActionKind.EXPAND_AIS_SEARCH not in attempted):
            return make(ActionKind.EXPAND_AIS_SEARCH,
                        "No AIS evidence has been gathered; candidate vessels are unknown.",
                        "attribution_uncertainty",
                        "Candidate vessel tracks retrieved for attribution.", 2)

        # 7. No source hypothesis yet -> what KIND of source is this?
        if (ledger.latest(case_id, EvidenceKind.SOURCE_HYPOTHESIS) is None
                and ActionKind.RUN_SOURCE_HYPOTHESIS not in attempted):
            return make(ActionKind.RUN_SOURCE_HYPOTHESIS,
                        "No source-class hypothesis exists; attributing to a vessel "
                        "before establishing that a vessel is even the likely source "
                        "class would beg the question.",
                        "attribution_uncertainty",
                        "Ranked source hypotheses produced by CHHAYA.", 3)

        # 8. Memory not consulted -> prior cases may hold relevant context.
        if (ledger.latest(case_id, EvidenceKind.MEMORY) is None
                and ActionKind.CONSULT_MEMORY not in attempted):
            return make(ActionKind.CONSULT_MEMORY,
                        "Prior similar cases have not been consulted; recurrence and "
                        "past failure patterns are unknown.",
                        "evidence_agreement",
                        "Advisory historical context attached (never overriding "
                        "current evidence).", 4)

        # 9. Attribution still highly uncertain after everything above.
        if (unc.attribution_uncertainty is not None
                and unc.attribution_uncertainty.value is not None
                and unc.attribution_uncertainty.value > 0.9
                and ActionKind.ESCALATE_TO_OPERATOR not in attempted):
            return make(ActionKind.ESCALATE_TO_OPERATOR,
                        f"Posterior entropy {unc.attribution_uncertainty.value:.2f} exceeds "
                        "0.9: the evidence cannot rank candidates, and further automated "
                        "steps would not change that.",
                        "attribution_uncertainty",
                        "Human judgement applied to an genuinely ambiguous case.", 1)

        # 10. Preconditions for proceeding. "Every action has been attempted" is
        # NOT the same claim as "the evidence is present" -- if the executor
        # failed, those actions are attempted-and-useless, and treating that as
        # readiness would be a fail-OPEN: the case would advance to a decision
        # on evidence that was never actually gathered. Check the evidence
        # itself, not the attempt log.
        missing: list[str] = []
        if unc.data_quality is None:
            missing.append("data-quality assessment")
        if unc.ood_risk is OODRisk.UNKNOWN:
            missing.append("OOD assessment")
        if missing:
            return make(ActionKind.STOP_INSUFFICIENT_EVIDENCE,
                        "Cannot certify the perception input: "
                        + " and ".join(missing)
                        + " could not be obtained (the corresponding action(s) were "
                        "attempted and did not produce evidence). Proceeding would "
                        "decide on unverified input.",
                        "data_quality" if unc.data_quality is None else "ood_risk",
                        "Case ends insufficient rather than deciding on unverified input.",
                        0)

        # 11. Everything available has genuinely been gathered.
        return make(ActionKind.PROCEED_TO_DECISION,
                    "All available evidence has been gathered and no unresolved "
                    "contradiction or unassessed uncertainty remains.",
                    unc.dominant_concern,
                    "Case proceeds to the Validity Gate and decision layer.", 0)


class AgenticLoop:
    """
    The controller. Owns no science: it decides *what to do next* and delegates
    every actual computation to the executor the Case Engine supplies.
    """

    def __init__(self, *, assessor: UncertaintyAssessor | None = None,
                 selector: ActionSelector | None = None,
                 max_iterations: int = DEFAULT_MAX_ITERATIONS) -> None:
        self.assessor = assessor or UncertaintyAssessor()
        self.selector = selector or ActionSelector()
        self.max_iterations = max_iterations

    def run(self, case_id: str, ledger: EvidenceLedger,
            executor: Executor | None = None) -> tuple[DecisionTrace, UncertaintyAssessment]:
        trace = DecisionTrace(case_id=case_id)
        attempted: set[ActionKind] = set()
        unc = self.assessor.assess(case_id, ledger)

        for i in range(self.max_iterations):
            n_before = len(ledger.for_case(case_id))
            trace.steps.append(DecisionStep(
                iteration=i, phase=LoopPhase.OBSERVE,
                note=f"{n_before} active evidence item(s) in the ledger.",
            ))

            unc = self.assessor.assess(case_id, ledger)
            trace.steps.append(DecisionStep(
                iteration=i, phase=LoopPhase.IDENTIFY_UNCERTAINTY,
                note=(f"dominant concern: {unc.dominant_concern}; "
                      f"conflicts: {unc.evidence_conflict_count}; "
                      f"ood: {unc.ood_risk.value}"),
                dominant_concern=unc.dominant_concern,
            ))

            action = self.selector.select(case_id, ledger, unc, attempted)
            trace.steps.append(DecisionStep(
                iteration=i, phase=LoopPhase.SELECT_ACTION,
                note=f"selected {action.kind.value} (priority {action.priority})",
                action=action,
            ))

            if action.kind.is_terminal:
                trace.terminal_action = action.kind
                trace.terminal_reason = action.because
                trace.steps.append(DecisionStep(
                    iteration=i, phase=LoopPhase.TERMINATE,
                    note=f"terminal action {action.kind.value}: {action.because}",
                    action=action,
                ))
                trace.iterations = i + 1
                return trace, unc

            attempted.add(action.kind)

            if executor is None:
                record = ActionRecord(
                    action=action, outcome=ActionOutcome.UNAVAILABLE,
                    result_summary=("No executor was supplied, so this action could not "
                                    "be carried out. Recorded as attempted so the loop "
                                    "does not re-select it."),
                    changed=False,
                )
            else:
                t0 = time.perf_counter()
                try:
                    record = executor(action, ledger)
                except Exception as exc:   # never let an executor kill the case
                    record = ActionRecord(
                        action=action, outcome=ActionOutcome.FAILED,
                        result_summary=f"Executor raised {type(exc).__name__}.",
                        error=str(exc), changed=False,
                        runtime_seconds=time.perf_counter() - t0,
                    )

            trace.steps.append(DecisionStep(
                iteration=i, phase=LoopPhase.EXECUTE,
                note=f"{action.kind.value} -> {record.outcome.value}",
                action=action, record=record,
            ))

            n_after = len(ledger.for_case(case_id))
            trace.steps.append(DecisionStep(
                iteration=i, phase=LoopPhase.UPDATE_EVIDENCE,
                note=(f"evidence {n_before} -> {n_after}"
                      + ("" if record.changed else " (no new evidence)")),
            ))

        trace.iterations = self.max_iterations
        trace.halted_on_budget = True
        trace.terminal_reason = (
            f"Reached the {self.max_iterations}-iteration budget without a terminal "
            "decision. Treated as insufficient evidence rather than as success."
        )
        trace.terminal_action = ActionKind.STOP_INSUFFICIENT_EVIDENCE
        return trace, unc
