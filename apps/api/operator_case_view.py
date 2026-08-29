"""
VARUNA GRID — Operator Case view builder.

Pure projection: `Case` (+ its praman artifacts) -> `OperatorCase`. No
science, no gate re-evaluation, no filesystem access — every value here is
either read verbatim off an existing typed contract already produced by a
backend stage (`case.metadata[...]`), or is an honest "not produced yet"
marker. See packages/varuna_contracts/operator_case.py for the contract
itself and docs/api/OPERATOR_CASE_CONTRACT_V1.md for the full write-up.

This module deliberately contains NO business logic: if you find yourself
computing a score, re-deriving a threshold, or inferring a missing value
here, that computation belongs in the producing subsystem instead.
"""
from __future__ import annotations

from datetime import datetime, timezone

from varuna_contracts.decision import AttributionResultV2, ValidityGateResult
from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.operator_case import (
    AISCandidateView,
    EvidenceComponentView,
    EvidenceHealthView,
    ObservationView,
    OperatorCase,
    ProducerStatus,
    ProvenanceView,
    SectionEnvelope,
    SystemStatusView,
)
from varuna_contracts.phi import PhiField
from varuna_contracts.schemas import BBox, VesselTrack
from varuna_domain.case_workflow import CaseWorkflow
from varuna_domain.entities import Case


def _bbox_from_points(lons: list[float], lats: list[float]) -> BBox | None:
    """Degenerate (single-point or empty) input has no well-formed BBox — return
    None rather than a zero-area box that would fail BBox's own validator or
    silently misrepresent a point as an area."""
    if not lons or not lats:
        return None
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    if min_lon >= max_lon or min_lat >= max_lat:
        return None
    return BBox(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)


def _observation_section(case: Case) -> SectionEnvelope[ObservationView]:
    inp = case.metadata.get("input")
    if inp is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="CaseWorkflow.ingest() has not run for this case.",
        )
    view = ObservationView(
        n_slick_points=len(inp["slick_lons"]),
        n_tracks=len(inp["tracks"]),
        obs_time_hours=inp["obs_time_hours"],
        bbox=_bbox_from_points(inp["slick_lons"], inp["slick_lats"]),
    )
    # The current per-case pipeline (CaseWorkflow.ingest) accepts already-
    # extracted slick points directly; it does not carry an EvidenceEnvelope
    # of its own. Reporting EvidenceMode here would be inventing provenance
    # that was never actually attached to the input. Honest answer: unknown
    # at this stage, not "simulated" and not "real".
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=view, evidence_mode=None)


def _detection_section(case: Case) -> SectionEnvelope:
    # NETRA scene inference is not wired into CaseWorkflow (case.metadata
    # never gains a "detection" key produced by NETRA) — the pipeline starts
    # from already-known slick points. This is a real, named gap, not a
    # silent omission: see docs/api/OPERATOR_CASE_CONTRACT_V1.md, "Missing
    # Backend Producers".
    detection = case.metadata.get("detection")
    if detection is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="NETRA_INFERENCE_NOT_WIRED_INTO_CASE_PIPELINE",
        )
    from varuna_contracts.schemas import SlickDetection
    value = SlickDetection.model_validate(detection)
    return SectionEnvelope(
        status=ProducerStatus.PRODUCED, value=value, evidence_mode=EvidenceMode.REAL,
    )


def _origin_section(case: Case) -> SectionEnvelope[PhiField]:
    phi_raw = case.metadata.get("phi")
    if phi_raw is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="CaseWorkflow.reconstruct() has not run for this case.",
        )
    phi = PhiField.model_validate(phi_raw)
    return SectionEnvelope(
        status=ProducerStatus.PRODUCED, value=phi, evidence_mode=phi.envelope.mode,
    )


def _ais_section(case: Case) -> SectionEnvelope[list[AISCandidateView]]:
    inp = case.metadata.get("input")
    if inp is None or not inp.get("tracks"):
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="No AIS tracks were ingested for this case.",
        )
    tracks = [VesselTrack.model_validate(t) for t in inp["tracks"]]
    views = [
        AISCandidateView(
            mmsi=t.mmsi, vessel_name=t.name, vessel_type=t.vessel_type,
            n_points=t.n_points, start_time=t.start_time, end_time=t.end_time,
            total_gap_minutes=t.total_gap_minutes, max_gap_minutes=t.max_gap_minutes,
            transponder_active=t.transponder_active,
        )
        for t in tracks
    ]
    # Track-level provenance/EvidenceMode is not currently attached to
    # VesselTrack itself (no envelope field on that contract) — honestly
    # unknown here rather than assumed REAL. Real AIS ingestion exists only
    # as a standalone script (scripts/ingest_real_ais*.py), not yet wired
    # through varuna_source_adapters.fetch_with_mode() into this pipeline.
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=views, evidence_mode=None)


def _attribution_section(case: Case) -> SectionEnvelope[AttributionResultV2]:
    attr_raw = case.metadata.get("attribution")
    if attr_raw is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="CaseWorkflow.attribute() has not run for this case.",
        )
    attribution = AttributionResultV2.model_validate(attr_raw)
    return SectionEnvelope(
        status=ProducerStatus.PRODUCED, value=attribution, evidence_mode=attribution.envelope.mode,
    )


def _validity_section(case: Case) -> SectionEnvelope[ValidityGateResult]:
    gate_raw = case.metadata.get("gate_result")
    if gate_raw is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="ValidityService.evaluate() has not run for this case.",
        )
    gate = ValidityGateResult.model_validate(gate_raw)
    status = ProducerStatus.PRODUCED if gate.allows_operational_action else ProducerStatus.BLOCKED
    return SectionEnvelope(status=status, value=gate, evidence_mode=gate.envelope.mode)


def _forecast_section(case: Case) -> SectionEnvelope:
    # PRAVAAH (varuna_pravaah.service.PravaahService) is a real, wired
    # subsystem — but CaseWorkflow never calls it, so no case ever carries
    # a "forecast" metadata key today. NOT_YET_PRODUCED reports that
    # workflow-integration gap honestly rather than fabricating a horizon.
    forecast_raw = case.metadata.get("forecast")
    if forecast_raw is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="PRAVAAH forecast is not yet wired into CaseWorkflow.",
        )
    from varuna_contracts.schemas import ForwardForecast
    value = ForwardForecast.model_validate(forecast_raw)
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=value, evidence_mode=None)


def _decision_section(case: Case) -> SectionEnvelope:
    # ABHIYAN (varuna_abhiyan.service.AbhiyanService) likewise exists but is
    # not called from CaseWorkflow.
    decision_raw = case.metadata.get("decision")
    if decision_raw is None:
        return SectionEnvelope(
            status=ProducerStatus.NOT_YET_PRODUCED,
            reason="ABHIYAN tasking is not yet wired into CaseWorkflow.",
        )
    from varuna_contracts.schemas import AssetTasking
    value = [AssetTasking.model_validate(t) for t in decision_raw]
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=value, evidence_mode=None)


def _mission_section(case: Case, workflow: CaseWorkflow) -> SectionEnvelope:
    # MissionService (varuna_missions.service) is a real, separately callable
    # subsystem but is not invoked as part of CaseWorkflow, and CaseWorkflow
    # holds no reference to a MissionRepository — so there is no honest way
    # to look up missions "for this case" from here without a caller
    # supplying that repository, which the read-only operator-view endpoint
    # does not currently do. Reporting NOT_YET_PRODUCED rather than
    # guessing at an empty list that would look identical to "checked, none
    # exist".
    return SectionEnvelope(
        status=ProducerStatus.NOT_YET_PRODUCED,
        reason="Mission FSM is not yet wired into CaseWorkflow/operator-view lookup.",
    )


def _alerts_section(case: Case) -> SectionEnvelope:
    # Same gap as mission: AlertService keeps its delivery log in its own
    # process-local instance, not on the case, and CaseWorkflow never routes
    # alerts. NOT_YET_PRODUCED, not an empty list.
    return SectionEnvelope(
        status=ProducerStatus.NOT_YET_PRODUCED,
        reason="Alert routing is not yet wired into CaseWorkflow.",
    )


def _evidence_health(
    observation: SectionEnvelope, detection: SectionEnvelope,
    origin: SectionEnvelope[PhiField], attribution: SectionEnvelope[AttributionResultV2],
    ais: SectionEnvelope,
) -> EvidenceHealthView:
    """
    Every component score is either read off a real computed value already
    on the underlying contract, or left `None` with an explicit reason —
    never a placeholder percentage. `sar`/`model_consistency` currently have
    no real computed score anywhere in the backend (NETRA confidence is
    per-detection and NETRA is not wired into this pipeline; there is no
    "model consistency" metric implemented anywhere), so they are honestly
    UNAVAILABLE rather than guessed.
    """
    components: list[EvidenceComponentView] = []

    components.append(EvidenceComponentView(
        component="sar",
        status=detection.status,
        score=detection.value.confidence if detection.value is not None else None,
        reason=detection.reason if detection.value is None else None,
        evidence_mode=detection.evidence_mode,
    ))

    if ais.status is ProducerStatus.PRODUCED:
        components.append(EvidenceComponentView(
            component="ais", status=ProducerStatus.PRODUCED,
            score=None,  # no completeness/quality metric is computed for AIS anywhere yet
            reason="No AIS completeness metric is computed by the current backend.",
            evidence_mode=ais.evidence_mode,
        ))
    else:
        components.append(EvidenceComponentView(
            component="ais", status=ais.status, score=None, reason=ais.reason,
        ))

    components.append(EvidenceComponentView(
        component="model_consistency",
        status=ProducerStatus.NOT_YET_PRODUCED,
        score=None,
        reason="No cross-model consistency check is implemented in the current backend.",
    ))

    if origin.status is ProducerStatus.PRODUCED and origin.value is not None:
        diag = origin.value.diagnostics
        # ensemble_completeness is a real, already-computed [0,1] quantity —
        # reused as the forcing/ensemble-quality score rather than inventing
        # a new metric.
        components.append(EvidenceComponentView(
            component="forcing", status=ProducerStatus.PRODUCED,
            score=diag.ensemble_completeness, evidence_mode=origin.evidence_mode,
        ))
    else:
        components.append(EvidenceComponentView(
            component="forcing", status=origin.status, score=None, reason=origin.reason,
        ))

    return EvidenceHealthView(components=components)


def _provenance(case: Case, workflow: CaseWorkflow, generated_at: datetime) -> ProvenanceView:
    artifacts = workflow.praman.list_by_case(case.case_id)
    manifest = next((a for a in artifacts if a.artifact_type == "evidence_manifest"), None)
    return ProvenanceView(
        case_id=case.case_id,
        artifact_ids=[a.artifact_id for a in artifacts],
        source_ids=sorted({a.produced_by for a in artifacts}),
        model_versions={},          # no per-model version registry is queried by CaseWorkflow today
        processing_versions={},
        manifest_artifact_id=manifest.artifact_id if manifest else None,
        generated_at=generated_at,
    )


def build_operator_case(case: Case, workflow: CaseWorkflow) -> OperatorCase:
    """The single entry point: real `Case` -> read-only `OperatorCase`."""
    generated_at = datetime.now(timezone.utc)

    observation = _observation_section(case)
    detection = _detection_section(case)
    origin = _origin_section(case)
    ais = _ais_section(case)
    attribution = _attribution_section(case)
    validity = _validity_section(case)
    forecast = _forecast_section(case)
    decision = _decision_section(case)
    mission = _mission_section(case, workflow)
    alerts = _alerts_section(case)

    return OperatorCase(
        case_id=case.case_id,
        generated_at=generated_at,
        system_status=SystemStatusView(
            case_status=case.status.value,
            scientific_status=case.scientific_status.value,
            error=case.error,
        ),
        observation=observation,
        detection=detection,
        origin=origin,
        ais=ais,
        attribution=attribution,
        validity=validity,
        forecast=forecast,
        decision=decision,
        mission=mission,
        alerts=alerts,
        evidence=_evidence_health(observation, detection, origin, attribution, ais),
        provenance=_provenance(case, workflow, generated_at),
    )
