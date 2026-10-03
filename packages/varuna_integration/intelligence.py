"""
VARUNA GRID — case intelligence layer.

Bridges the canonical `RealE2EPipeline`/`GoldenCaseWorkflow` output into the
evidence/reasoning stack added in the product-build phase:

    PipelineRun -> Evidence Ledger -> UncertaintyAssessment
                -> agentic loop (CHHAYA / SMRITI executors)
                -> DetectionEvidenceEnvelope -> PRAMAN record

**This is not a second pipeline.** It runs no science of its own: no
advection, no attribution, no gate. It *reads* what the canonical pipeline
already produced, records it as evidence, and reasons about what is missing.
Every scientific value it publishes is copied from a stage the pipeline ran,
with its `EvidenceMode` carried through unchanged.

The one thing it does add is honesty plumbing: OOD assessment, the
detection-evidence envelope, and the source-hypothesis/memory steps, none of
which existed as recorded evidence before.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from varuna_agentic.loop import AgenticLoop, UncertaintyAssessor
from varuna_chhaya.hypothesis_engine import (
    GULF_OF_MEXICO_PRIORS, SourceHypothesisEngine,
)
from varuna_contracts.action import (
    ActionKind, ActionOutcome, ActionRecord, DecisionTrace, NextBestAction,
)
from varuna_contracts.detection_evidence import (
    DetectionEvidenceEnvelope, Measured, MeasurementStatus, OODRisk,
    UncertaintyAssessment,
)
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.source_hypothesis import SourceHypothesisEnvelope
from varuna_evidence.ledger import EvidenceKind, EvidenceLedger
from varuna_integration.stage import StageStatus
from varuna_smriti.memory import CaseMemory, SmritiStore

# Stage name in PipelineRun -> the evidence kind it becomes in the ledger.
STAGE_TO_EVIDENCE_KIND: dict[str, EvidenceKind] = {
    "forcing": EvidenceKind.FORCING,
    "netra_detection": EvidenceKind.DETECTION,
    "ais_ingest": EvidenceKind.AIS,
    "phi_reconstruction": EvidenceKind.ORIGIN,
    "attribution": EvidenceKind.ATTRIBUTION,
    "validity": EvidenceKind.VALIDITY,
    "forecast": EvidenceKind.FORECAST,
    "decision": EvidenceKind.DECISION,
}

# The MC20 basin. Named explicitly by the caller rather than inferred from
# coordinates, so a regional prior is never applied by accident.
GULF_OF_MEXICO_BBOX = (-98.0, 18.0, -80.0, 31.0)   # min_lon, min_lat, max_lon, max_lat


@dataclass
class CaseIntelligence:
    """Everything the reasoning layer produced for one case."""
    case_id: str
    ledger: EvidenceLedger
    uncertainty: UncertaintyAssessment
    trace: DecisionTrace
    detection_evidence: DetectionEvidenceEnvelope | None = None
    hypotheses: SourceHypothesisEnvelope | None = None
    memory_hits: list[dict] = field(default_factory=list)
    runtime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "evidence_mode": (self.ledger.worst_mode(self.case_id).value
                              if self.ledger.worst_mode(self.case_id) else None),
            "uncertainty": {
                "dominant_concern": self.uncertainty.dominant_concern,
                "ood_risk": self.uncertainty.ood_risk.value,
                "conflicts": self.uncertainty.evidence_conflict_count,
                "notes": self.uncertainty.component_notes,
            },
            "terminal_action": (self.trace.terminal_action.value
                                if self.trace.terminal_action else None),
            "terminal_reason": self.trace.terminal_reason,
            "iterations": self.trace.iterations,
            "detection_evidence": (self.detection_evidence.model_dump(mode="json")
                                   if self.detection_evidence else None),
            "hypotheses": (self.hypotheses.model_dump(mode="json")
                           if self.hypotheses else None),
            "memory_hits": self.memory_hits,
            "audit_trail": self.ledger.audit_trail(self.case_id),
            "decision_trace": self.trace.render(),
            "runtime_seconds": self.runtime_seconds,
        }


_OOD_RISK_BY_LABEL = {
    "in_domain": OODRisk.IN_DOMAIN,
    "borderline": OODRisk.BORDERLINE,
    "out_of_domain": OODRisk.OUT_OF_DOMAIN,
    "unknown": OODRisk.UNKNOWN,
}


def assess_ood_from_detection(stage_detail: dict, produced: bool) -> tuple[OODRisk, str]:
    """
    Classify OOD risk from what the detection stage actually reported.

    Combines two independent, no-training signals via
    `varuna_integration.ood_energy.combine_ood_signals()`:

    1. The class-probability heuristic (`max_probability` vs.
       `decision_threshold`) — reflects only the oil-class probability.
    2. The energy-score signal (`min_energy` vs. a reference distribution
       built from NETRA-GOLD-v0.2 val tiles) — reflects whether the model's
       raw, all-class representation of this input resembles its training
       domain, independent of which class wins.

    Neither is a calibrated OOD detector, and the combiner says so. When the
    two disagree, that disagreement is reported explicitly rather than
    resolved by preferring one signal — see `ood_energy.combine_ood_signals`.
    """
    max_prob = stage_detail.get("max_probability")
    threshold = stage_detail.get("decision_threshold")
    min_energy = stage_detail.get("min_energy")

    if not produced and max_prob is None and min_energy is None:
        return (OODRisk.UNKNOWN,
                "The detector reported no detection and no activation statistics, "
                "so no OOD judgement is possible from this run alone.")

    from varuna_integration.ood_energy import combine_ood_signals
    label, rationale = combine_ood_signals(
        max_probability=max_prob, decision_threshold=threshold, min_energy=min_energy,
    )
    return _OOD_RISK_BY_LABEL[label], rationale


def build_detection_evidence(case_id: str, run_id: str | None,
                             stage, parent_envelope: EvidenceEnvelope
                             ) -> DetectionEvidenceEnvelope:
    """Turn the pipeline's detection stage into structured evidence."""
    detail = stage.detail or {}
    produced = stage.status is StageStatus.PRODUCED
    ood, rationale = assess_ood_from_detection(detail, produced)

    detection = stage.value[0] if (produced and stage.value) else None
    limitations: list[str] = []
    if not produced:
        limitations.append(f"No detection produced: {stage.reason}")
    if detail.get("scientific_status"):
        limitations.append(f"Model scientific status: {detail['scientific_status']}")
    if ood is OODRisk.OUT_OF_DOMAIN:
        limitations.append(
            "Detector is operating out-of-domain; its confidence must not be "
            "treated as a calibrated probability.")

    def measured(value, status=MeasurementStatus.MEASURED, units=None):
        if value is None:
            return Measured(value=None, status=MeasurementStatus.UNAVAILABLE, units=units)
        return Measured(value=float(value), status=status, units=units)

    return DetectionEvidenceEnvelope(
        evidence_id=f"detev-{case_id}",
        case_id=case_id,
        run_id=run_id,
        model_id="netra",
        model_version=detail.get("model_version", "unknown"),
        checkpoint_sha256=detail.get("checkpoint_sha256"),
        preprocessing_version=detail.get("preprocessing_version"),
        channel_binding=detail.get("channel_binding", []),
        n_tiles=int(detail.get("n_tiles", 0) or 0),
        classification=(detection.classification.value if detection else None),
        confidence=measured(detection.confidence if detection else None),
        decision_threshold=measured(detail.get("decision_threshold")),
        area_km2=measured(detection.area_km2 if detection else None, units="km^2"),
        centroid=(detection.centroid if detection else None),
        bbox=(detection.bbox if detection else None),
        score_max=measured(detail.get("max_probability")),
        ood_risk=ood,
        ood_rationale=rationale,
        low_wind_context=measured(detail.get("mean_wind_speed_ms"), units="m/s"),
        limitations=limitations,
        observed_at=(detection.observation_time if detection else None),
        envelope=parent_envelope.derive(
            artifact_id=f"detev-{case_id}", produced_by="netra.detection_evidence",
            model_version=detail.get("model_version"),
        ),
    )


def _pipeline_run_data_quality(run) -> dict:
    """M4 fix (docs/product/HONESTY_LEDGER.md #6): the golden/replay path
    never ran any data-quality check at all — `varuna_data_guard.guard
    .evaluate_data_guard()` is only ever called from the legacy
    `CaseWorkflow.ingest()` path.

    This is deliberately NOT a call to that same function. Its checks are
    scoped to `CaseWorkflow.ingest()`'s own conventions and would misfire
    here: `obs_time_hours > 0` is checked against a positive synthetic
    float there, but the golden/replay path's closest analogue is Phi's
    epoch-relative coordinate (`ObservationView.phi_time_coordinate_hours`),
    which is legitimately NEGATIVE for a historical replay case (see the
    M3 fix) — every Indian-Ocean fixture would show as "quarantined" by
    construction. Likewise, `slick_point_count >= 10` assumes a real
    per-pixel mask contour; replay fixtures represent a slick with one
    anchor point by design, not a fabricated one.

    So: check what is actually meaningful for a composed run —
    points/tracks present, and the real wall-clock `observation_time` (not
    the Phi coordinate) is not in the future, exactly the invariant M4
    called for ("you cannot observe the future"). Never blocks the
    pipeline; this is visibility recorded as evidence, not a second gate —
    see `varuna_data_guard.guard`'s own module for why a gate belongs at
    the legacy ingest boundary and not duplicated here.
    """
    checks = []

    # `PipelineRun.slick_points` defaults to `()` (present but empty) when
    # no detection ever ran, not absent — `getattr(..., default)` doesn't
    # catch that case, only a genuinely missing attribute.
    lons, _lats = getattr(run, "slick_points", None) or ([], [])
    n_points = len(lons)
    checks.append({"name": "slick_points_present", "passed": n_points > 0, "observed": n_points})

    ais = run.stages.get("ais_ingest")
    n_tracks = len(ais.value) if (ais is not None and ais.status is StageStatus.PRODUCED and ais.value) else 0
    checks.append({"name": "ais_ingest_ran", "passed": ais is not None, "observed": n_tracks})

    det = run.stages.get("netra_detection")
    obs_time = None
    if det is not None and det.status is StageStatus.PRODUCED and det.value:
        obs_time = getattr(det.value[0], "observation_time", None)
    time_ok = obs_time is not None and obs_time <= datetime.now(timezone.utc)
    checks.append({
        "name": "observation_time_not_future", "passed": time_ok,
        "observed": obs_time.isoformat() if obs_time else None,
    })

    blocking = [c["name"] for c in checks if not c["passed"]]
    return {
        "verdict": "accepted" if not blocking else "degraded",
        "checks": checks,
        "blocking": blocking,
    }


def ledger_from_run(run, *, case_id: str | None = None) -> EvidenceLedger:
    """
    Project a `PipelineRun` into the Evidence Ledger.

    Only stages that actually produced something become evidence. A stage that
    reported NOT_YET_PRODUCED/BLOCKED is deliberately NOT recorded as an
    evidence item — recording "nothing happened" as evidence would let the
    ledger's own item count imply the case is better supported than it is. Its
    reason is preserved on the pipeline run itself, which is the audit surface
    for stage outcomes.
    """
    cid = case_id or run.case_id
    ledger = EvidenceLedger()
    forcing_id: str | None = None

    for stage_name, kind in STAGE_TO_EVIDENCE_KIND.items():
        stage = run.stages.get(stage_name)
        if stage is None or stage.status is not StageStatus.PRODUCED:
            continue
        depends = [forcing_id] if (forcing_id and stage_name != "forcing") else []
        item = ledger.append(
            case_id=cid, kind=kind, produced_by=f"pipeline.{stage_name}",
            summary=f"{stage_name} produced",
            mode=stage.evidence_mode or EvidenceMode.UNAVAILABLE,
            observation=_observation_for(stage_name, stage),
            confidence=_confidence_for(stage_name, stage),
            depends_on=depends,
        )
        if stage_name == "forcing":
            forcing_id = item.evidence_id
    return ledger


def _observation_for(stage_name: str, stage) -> dict:
    detail = dict(stage.detail or {})
    if stage_name == "netra_detection":
        ood, _ = assess_ood_from_detection(detail, True)
        detail["ood_risk"] = ood.value
    if stage_name == "attribution" and stage.value is not None:
        detail["posterior_entropy"] = getattr(stage.value, "posterior_entropy", None)
    return {k: v for k, v in detail.items() if _jsonable(v)}


def _confidence_for(stage_name: str, stage) -> float | None:
    if stage_name == "netra_detection" and stage.value:
        return float(stage.value[0].confidence)
    return None


def _jsonable(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool, type(None), list, dict))


class CaseIntelligenceService:
    """
    Runs the reasoning layer over a completed `PipelineRun`.

    Executors are real: CHHAYA actually runs, SMRITI actually reads and writes
    the memory store. Actions whose capability genuinely does not exist in
    this build return `ActionOutcome.UNAVAILABLE` rather than a fabricated
    success — which is what makes the loop's fail-closed guard meaningful.
    """

    def __init__(self, *, smriti: SmritiStore | None = None,
                 chhaya: SourceHypothesisEngine | None = None,
                 max_iterations: int = 8) -> None:
        self.smriti = smriti
        self.chhaya = chhaya or SourceHypothesisEngine()
        self.loop = AgenticLoop(max_iterations=max_iterations)
        self.assessor = UncertaintyAssessor()

    def run(self, run, *, case_id: str | None = None) -> CaseIntelligence:
        t0 = time.perf_counter()
        cid = case_id or run.case_id
        ledger = ledger_from_run(run, case_id=cid)

        parent = EvidenceEnvelope(
            artifact_id=f"intel-parent-{cid}", case_id=cid,
            produced_by="varuna_integration.intelligence",
            provenance=Provenance(source_id="varuna.case_intelligence"),
            mode=ledger.worst_mode(cid) or EvidenceMode.UNAVAILABLE,
        )

        # M4 fix (docs/product/HONESTY_LEDGER.md #6): the data guard never
        # ran on the golden/replay path at all. Recorded as evidence, never
        # blocking — see `_pipeline_run_data_quality()`'s own docstring for
        # why this isn't a call to `varuna_data_guard.guard
        # .evaluate_data_guard()` itself.
        dq = _pipeline_run_data_quality(run)
        ledger.append(
            case_id=cid, kind=EvidenceKind.DATA_QUALITY, produced_by="pipeline_run_data_quality",
            summary=f"data quality: {dq['verdict']}"
                    + (f" ({', '.join(dq['blocking'])} failed)" if dq["blocking"] else ""),
            mode=parent.mode,
            observation=dq,
        )

        detection_stage = run.stages.get("netra_detection")
        detection_evidence = (
            build_detection_evidence(cid, run.run_id, detection_stage, parent)
            if detection_stage is not None else None
        )

        # If an OOD judgement is already available from the detection stage's
        # activation statistics, record it BEFORE the loop runs. The loop can
        # terminate on "no detection" without ever reaching ASSESS_OOD, and an
        # OOD finding that was actually made must not be lost just because the
        # case ended early -- that is the MC20 situation exactly.
        if (detection_evidence is not None
                and detection_evidence.ood_risk is not OODRisk.UNKNOWN):
            ledger.append(
                case_id=cid, kind=EvidenceKind.DATA_QUALITY, produced_by="ood_assessor",
                summary=f"OOD risk: {detection_evidence.ood_risk.value}",
                mode=detection_stage.evidence_mode or EvidenceMode.REAL,
                observation={"ood_risk": detection_evidence.ood_risk.value,
                             "rationale": detection_evidence.ood_rationale},
            )

        state: dict[str, Any] = {"hypotheses": None, "memory_hits": []}
        executor = self._make_executor(cid, run, parent, detection_evidence, state)

        trace, uncertainty = self.loop.run(cid, ledger, executor=executor)

        return CaseIntelligence(
            case_id=cid, ledger=ledger, uncertainty=uncertainty, trace=trace,
            detection_evidence=detection_evidence,
            hypotheses=state["hypotheses"], memory_hits=state["memory_hits"],
            runtime_seconds=time.perf_counter() - t0,
        )

    # ------------------------------------------------------------- executors

    def _make_executor(self, cid, run, parent, detection_evidence, state):
        def execute(action: NextBestAction, ledger: EvidenceLedger) -> ActionRecord:
            handler = {
                ActionKind.INSPECT_DETECTION_QUALITY: self._inspect_quality,
                ActionKind.ASSESS_OOD: self._assess_ood,
                ActionKind.RUN_SOURCE_HYPOTHESIS: self._run_chhaya,
                ActionKind.CONSULT_MEMORY: self._consult_memory,
            }.get(action.kind)
            if handler is None:
                # Genuinely not available in this build. Reported honestly so
                # the loop's fail-closed guard can act on it, rather than
                # returning a success that produced nothing.
                return ActionRecord(
                    action=action, outcome=ActionOutcome.UNAVAILABLE,
                    result_summary=(
                        f"{action.kind.value} is not executable from the intelligence "
                        "layer: it is a pipeline stage that already ran (or did not) "
                        "during the canonical run, and re-running it here would "
                        "duplicate orchestration."),
                    changed=False)
            return handler(action, ledger, cid, run, parent, detection_evidence, state)
        return execute

    def _inspect_quality(self, action, ledger, cid, run, parent, det_ev, state):
        """Record the data-guard verdict already implied by the pipeline stages."""
        forcing = run.stages.get("forcing")
        det = run.stages.get("netra_detection")
        ok = forcing is not None and forcing.status is StageStatus.PRODUCED
        confidence = 0.9 if ok else 0.1
        summary = ("Inputs accepted: real forcing loaded"
                   if ok else f"Input problem: forcing stage says {forcing.reason if forcing else 'absent'}")
        item = ledger.append(
            case_id=cid, kind=EvidenceKind.DATA_QUALITY, produced_by="data_guard",
            summary=summary, mode=(forcing.evidence_mode if forcing else EvidenceMode.UNAVAILABLE)
            or EvidenceMode.UNAVAILABLE,
            confidence=confidence,
            observation={"forcing_status": forcing.status.value if forcing else "absent",
                         "detection_status": det.status.value if det else "absent"},
        )
        return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                            result_summary=summary, evidence_added=[item.evidence_id],
                            changed=True)

    def _assess_ood(self, action, ledger, cid, run, parent, det_ev, state):
        if det_ev is None:
            return ActionRecord(action=action, outcome=ActionOutcome.UNAVAILABLE,
                                result_summary="No detection evidence to assess.",
                                changed=False)
        detection = ledger.latest(cid, EvidenceKind.DETECTION)
        if detection is None:
            # The detection stage produced nothing, so there is no ledger item
            # to annotate. Record the OOD judgement as its own evidence.
            item = ledger.append(
                case_id=cid, kind=EvidenceKind.DATA_QUALITY, produced_by="ood_assessor",
                summary=f"OOD risk: {det_ev.ood_risk.value}", mode=EvidenceMode.REAL,
                observation={"ood_risk": det_ev.ood_risk.value,
                             "rationale": det_ev.ood_rationale},
            )
            return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                                result_summary=det_ev.ood_rationale,
                                evidence_added=[item.evidence_id], changed=True)
        obs = dict(detection.observation)
        obs["ood_risk"] = det_ev.ood_risk.value
        obs["ood_rationale"] = det_ev.ood_rationale
        revised = ledger.revise(detection.evidence_id, observation=obs,
                                produced_by="ood_assessor")
        return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                            result_summary=det_ev.ood_rationale,
                            evidence_added=[revised.evidence_id], changed=True)

    def _run_chhaya(self, action, ledger, cid, run, parent, det_ev, state):
        detection = ledger.latest(cid, EvidenceKind.DETECTION)
        ais = run.stages.get("ais_ingest")
        ais_detail = (ais.detail or {}) if ais is not None else {}
        closest = ais_detail.get("closest_temporally_matched") or {}
        netra_stage = run.stages.get("netra_detection")
        raw_detection = (netra_stage.value[0]
                        if netra_stage is not None and netra_stage.value else None)
        phi_stage = run.stages.get("phi_reconstruction")

        centroid = det_ev.centroid if det_ev else None
        # Previously computed and then discarded: `corridor` was queried on
        # every case and never passed to `engine.assess()`, so
        # `prior_cases_same_corridor` silently stayed at its default 0
        # regardless of what SMRITI actually found. Found during Phase 0
        # reconnaissance of this hardening session; fixed here.
        corridor = 0
        if self.smriti is not None and centroid is not None:
            corridor = self.smriti.corridor_case_count(centroid.lon, centroid.lat, 50.0)

        in_gom = bool(centroid is not None and
                      GULF_OF_MEXICO_BBOX[0] <= centroid.lon <= GULF_OF_MEXICO_BBOX[2] and
                      GULF_OF_MEXICO_BBOX[1] <= centroid.lat <= GULF_OF_MEXICO_BBOX[3])
        engine = (SourceHypothesisEngine(priors=GULF_OF_MEXICO_PRIORS,
                                         region_note="Gulf of Mexico: documented persistent seepage")
                  if in_gom else self.chhaya)

        # Wind speed and area come from `det_ev` (DetectionEvidenceEnvelope),
        # which already carries them as `Measured` — pass the value only when
        # actually measured, never a default standing in for absence.
        wind_speed_ms = (det_ev.low_wind_context.value
                        if det_ev and det_ev.low_wind_context
                        and det_ev.low_wind_context.status.value == "measured"
                        else None)
        area_km2 = (det_ev.area_km2.value
                   if det_ev and det_ev.area_km2
                   and det_ev.area_km2.status.value == "measured"
                   else None)
        # `elongation` lives on the raw `SlickDetection`, not on
        # `DetectionEvidenceEnvelope` (which has no such field) — read it
        # from the stage's own value rather than fabricating it.
        elongation = getattr(raw_detection, "elongation", None)

        phi_available = phi_stage is not None and phi_stage.status.value == "produced"
        phi_converged = None
        if phi_available:
            flag = (phi_stage.detail or {}).get("convergence_flag")
            phi_converged = (flag == "converged") if flag is not None else None

        hyp = engine.assess(
            case_id=cid, parent_envelope=parent,
            detection_present=detection is not None,
            elongation=elongation,
            area_km2=area_km2,
            nearest_vessel_km=closest.get("distance_km"),
            nearest_vessel_temporally_matched=bool(closest),
            n_ais_tracks=ais_detail.get("n_returned") if ais is not None else None,
            in_known_seep_basin=in_gom,
            wind_speed_ms=wind_speed_ms,
            phi_available=phi_available,
            phi_converged=phi_converged,
            prior_cases_same_corridor=corridor,
            contradictions=[c.note or f"{c.left_summary} vs {c.right_summary}"
                            for c in ledger.contradictions(cid)],
            # M6 fix (docs/product/HONESTY_LEDGER.md #8): bucket by the
            # already-correct `EvidenceKind` on each ledger item, rather
            # than handing every factor the case's entire evidence list.
            # `SourceHypothesisEngine.assess()` looks each factor's evidence
            # up by the matching bucket key (see its own docstring), so
            # e.g. `no_ais_coverage` now carries only AIS evidence ids.
            evidence_ids={
                "ais": [i.evidence_id for i in ledger.for_case(cid) if i.kind == EvidenceKind.AIS],
                "detection": [i.evidence_id for i in ledger.for_case(cid) if i.kind == EvidenceKind.DETECTION],
                "phi": [i.evidence_id for i in ledger.for_case(cid) if i.kind == EvidenceKind.ORIGIN],
                "smriti": [i.evidence_id for i in ledger.for_case(cid) if i.kind == EvidenceKind.MEMORY],
                "contradictions": [ref for c in ledger.contradictions(cid)
                                   for ref in (c.left_id, c.right_id) if ref],
            },
        )
        state["hypotheses"] = hyp
        item = ledger.append(
            case_id=cid, kind=EvidenceKind.SOURCE_HYPOTHESIS, produced_by="chhaya",
            summary=f"top hypothesis: {hyp.top.source_class.value} "
                    f"({hyp.top.posterior:.2f})",
            mode=hyp.envelope.mode, confidence=hyp.top.posterior,
            observation={"method": hyp.method.value,
                         "engine_version": hyp.engine_version,
                         "insufficient_evidence": hyp.insufficient_evidence,
                         "ranked": [{"class": h.source_class.value,
                                     "posterior": h.posterior}
                                    for h in hyp.hypotheses]},
        )
        return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                            result_summary=f"CHHAYA: {hyp.top.source_class.value} "
                                           f"at {hyp.top.posterior:.2f}",
                            evidence_added=[item.evidence_id], changed=True)

    def _consult_memory(self, action, ledger, cid, run, parent, det_ev, state):
        if self.smriti is None:
            return ActionRecord(action=action, outcome=ActionOutcome.UNAVAILABLE,
                                result_summary="No SMRITI store is configured.",
                                changed=False)
        centroid = det_ev.centroid if det_ev else None
        query = CaseMemory(
            case_id=cid,
            centroid_lon=centroid.lon if centroid else None,
            centroid_lat=centroid.lat if centroid else None,
            observed_at=det_ev.observed_at if det_ev else None,
            top_source_class=(state["hypotheses"].top.source_class.value
                              if state["hypotheses"] else None),
        )
        retrieval = self.smriti.retrieve_similar_cases(query, limit=5)
        state["memory_hits"] = [
            {"case_id": h.memory.case_id, "score": round(h.similarity.score, 3),
             "coverage": round(h.similarity.coverage, 3),
             "outcome": h.memory.outcome,
             "provenance_source": h.memory.provenance_source,
             # Phase 7: the per-component breakdown that produced `score`,
             # captured at retrieval time so an operator's later "was this
             # useful" feedback can be attributed to the exact components
             # that drove THIS match, not a re-derived (possibly different)
             # one computed at feedback-submission time.
             "components": dict(h.similarity.components)}
            for h in retrieval.hits
        ]
        item = ledger.append(
            case_id=cid, kind=EvidenceKind.MEMORY, produced_by="smriti",
            summary=f"{len(retrieval.hits)} similar prior case(s) retrieved "
                    "(advisory only)",
            mode=EvidenceMode.REAL,
            observation={"advisory_only": retrieval.advisory_only,
                         "hits": state["memory_hits"],
                         "note": retrieval.note},
        )
        return ActionRecord(action=action, outcome=ActionOutcome.EXECUTED,
                            result_summary=f"{len(retrieval.hits)} prior case(s), advisory only",
                            evidence_added=[item.evidence_id], changed=True)
