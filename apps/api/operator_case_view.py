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
    OperationalDecisionState,
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
    observation_time = inp.get("observation_time")
    view = ObservationView(
        n_slick_points=len(inp["slick_lons"]),
        n_tracks=len(inp["tracks"]),
        phi_time_coordinate_hours=inp["obs_time_hours"],
        observation_time=(
            datetime.fromisoformat(observation_time) if observation_time else None
        ),
        bbox=_bbox_from_points(inp["slick_lons"], inp["slick_lats"]),
    )
    # The current per-case pipeline (CaseWorkflow.ingest) accepts already-
    # extracted slick points directly; it does not carry an EvidenceEnvelope
    # of its own. Reporting EvidenceMode here would be inventing provenance
    # that was never actually attached to the input. Honest answer: unknown
    # at this stage, not "simulated" and not "real".
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=view, evidence_mode=None)


def _section_payload(case: Case, key: str) -> dict | None:
    """The `{status, evidence_mode, reason, value}` envelope written by
    `varuna_integration.case_bridge.apply_run_to_case()`, if the pipeline ran.

    Absent for cases built by the older `CaseWorkflow.ingest/reconstruct/
    attribute` path, which predates the bridge — callers fall back to reading
    the bare metadata key in that case.
    """
    payload = case.metadata.get(f"{key}_section")
    return payload if isinstance(payload, dict) else None


def _mode_of(payload: dict | None) -> EvidenceMode | None:
    """Read a section's provenance. Never defaults to REAL.

    A missing mode means "honestly unknown", which is a different claim from
    "real" — defaulting here is how a simulated placeholder would silently be
    relabelled as real evidence.
    """
    if not payload:
        return None
    raw = payload.get("evidence_mode")
    return EvidenceMode(raw) if raw else None


def _status_of(payload: dict | None, default: ProducerStatus) -> ProducerStatus:
    if not payload:
        return default
    raw = str(payload.get("status", "")).lower()
    if raw == "produced":
        return ProducerStatus.PRODUCED
    if raw == "blocked":
        return ProducerStatus.BLOCKED
    if raw == "not_yet_produced":
        return ProducerStatus.NOT_YET_PRODUCED
    return default


def _detection_section(case: Case) -> SectionEnvelope:
    payload = _section_payload(case, "detection")
    detection = case.metadata.get("detection")
    if detection is None:
        return SectionEnvelope(
            status=_status_of(payload, ProducerStatus.NOT_YET_PRODUCED),
            reason=(payload or {}).get("reason")
            or "NETRA_INFERENCE_NOT_WIRED_INTO_CASE_PIPELINE",
        )
    from varuna_contracts.schemas import SlickDetection
    value = SlickDetection.model_validate(detection)
    # Provenance comes from the stage that produced the detection. It used to
    # be hardcoded to REAL here, which would have promoted an explicitly
    # simulated placeholder to real evidence the moment NETRA was wired in.
    return SectionEnvelope(
        status=ProducerStatus.PRODUCED, value=value, evidence_mode=_mode_of(payload),
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
    # `VesselTrack` still carries no per-track envelope, so track-level
    # provenance is not readable off the contract itself. What IS available now
    # is the ingest stage's own mode: real AIS reaches this pipeline through
    # `varuna_integration.ais_source.EventAISAdapter` via
    # `fetch_with_mode()`, so a case built by that path records REAL here.
    # Cases built by the older ingest path have no such record and stay None
    # (honestly unknown) rather than being assumed real.
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=views,
                           evidence_mode=_mode_of(_section_payload(case, "ais")))


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
    payload = _section_payload(case, "forecast")
    # `is None`, not truthiness: a legitimately empty-but-produced list must not
    # be swallowed into "never ran". Dormant today (producers report an empty
    # result as NOT_YET_PRODUCED with a reason) but the pattern is fragile.
    raw = (payload or {}).get("value")
    if raw is None:
        raw = case.metadata.get("forecast")
    if raw is None:
        return SectionEnvelope(
            status=_status_of(payload, ProducerStatus.NOT_YET_PRODUCED),
            reason=(payload or {}).get("reason")
            or "PRAVAAH forecast is not yet wired into CaseWorkflow.",
        )
    from varuna_contracts.schemas import ForwardForecast
    value = ForwardForecast.model_validate(raw)
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=value,
                           evidence_mode=_mode_of(payload))


def _decision_section(case: Case) -> SectionEnvelope:
    payload = _section_payload(case, "decision")
    raw = (payload or {}).get("value")
    if raw is None:
        raw = case.metadata.get("decision")
    if raw is None:
        # ABHIYAN returning zero taskings because the validity gate restricted
        # action is a real, correct outcome — the reason string carries that
        # distinction rather than looking like "never ran".
        return SectionEnvelope(
            status=_status_of(payload, ProducerStatus.NOT_YET_PRODUCED),
            reason=(payload or {}).get("reason")
            or "ABHIYAN tasking is not yet wired into CaseWorkflow.",
        )
    from varuna_contracts.schemas import AssetTasking
    value = [AssetTasking.model_validate(t) for t in raw]
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=value,
                           evidence_mode=_mode_of(payload))


def _mission_section(case: Case, workflow: CaseWorkflow) -> SectionEnvelope:
    payload = _section_payload(case, "mission")
    raw = (payload or {}).get("value")   # `is None` below, not truthiness
    if raw is None:
        return SectionEnvelope(
            status=_status_of(payload, ProducerStatus.NOT_YET_PRODUCED),
            reason=(payload or {}).get("reason")
            or "Mission FSM is not yet wired into CaseWorkflow/operator-view lookup.",
        )
    from varuna_contracts.states import MissionRecord
    value = [MissionRecord.model_validate(m) for m in raw]
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=value,
                           evidence_mode=_mode_of(payload))


def _alerts_section(case: Case) -> SectionEnvelope:
    payload = _section_payload(case, "alerts")
    raw = (payload or {}).get("value")   # `is None` below, not truthiness
    if raw is None:
        return SectionEnvelope(
            status=_status_of(payload, ProducerStatus.NOT_YET_PRODUCED),
            reason=(payload or {}).get("reason")
            or "Alert routing is not yet wired into CaseWorkflow.",
        )
    # DeliveryResult is a dataclass, not a pydantic contract, and `AlertView`
    # is the operator-facing shape — map the fields that exist rather than
    # inventing a delivery claim. `is_simulated` is carried through verbatim:
    # a simulated channel must never read as a delivered alert.
    from varuna_contracts.operator_case import AlertDeliveryStatus, AlertView

    def _delivery_status(r: dict) -> AlertDeliveryStatus:
        """`DeliveryResult.status` is "sent"/"suppressed"/"simulated"/"expired".

        A "sent" result on a simulated channel is NOT a delivery — `is_simulated`
        wins, exactly as AlertDeliveryStatus's own docstring requires. An
        unrecognised status degrades to UNAVAILABLE rather than DELIVERED.
        """
        raw_status = str(r.get("status", "")).lower()
        if bool(r.get("is_simulated", True)):
            return AlertDeliveryStatus.SIMULATED
        return {
            "sent": AlertDeliveryStatus.DELIVERED,
            "delivered": AlertDeliveryStatus.DELIVERED,
            "queued": AlertDeliveryStatus.QUEUED,
            "generated": AlertDeliveryStatus.GENERATED,
            "suppressed": AlertDeliveryStatus.SUPPRESSED,
            "expired": AlertDeliveryStatus.EXPIRED,
            "failed": AlertDeliveryStatus.FAILED,
        }.get(raw_status, AlertDeliveryStatus.UNAVAILABLE)

    from varuna_alerts.severity import infer_severity

    # `detail.event_type` is written by the alerts pipeline stage
    # (varuna_integration.pipeline._alerts) — honestly None for alerts
    # assembled without that detail available. Not read off the
    # channel-specific idempotency_key, whose format varies per channel.
    category = ((payload or {}).get("detail") or {}).get("event_type")

    views = [
        AlertView(
            channel=r.get("channel", "unknown"),
            recipient=r.get("recipient", "unknown"),
            category=category,
            delivery_status=_delivery_status(r),
            severity=infer_severity(
                suppressed=str(r.get("status", "")).lower() in ("suppressed", "expired"),
                is_simulated=bool(r.get("is_simulated", True)),
            ),
            reason=r.get("reason") or "",
            is_simulated=bool(r.get("is_simulated", True)),
            idempotency_key=r.get("idempotency_key", ""),
            timestamp=r.get("timestamp") or datetime.now(timezone.utc),
        )
        for r in raw
    ]
    return SectionEnvelope(status=ProducerStatus.PRODUCED, value=views,
                           evidence_mode=_mode_of(payload))


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

    # A case produced by the Track 4 pipeline registers no PRAMAN artifacts, so
    # the registry alone yields an empty lineage even though each producer
    # reported its own version and source. `pipeline_provenance` carries what
    # the stages actually said; it is merged with, not substituted for, the
    # registry so a CaseWorkflow-produced case is unaffected. Absent that key
    # the block stays empty rather than inventing a version.
    pipeline_prov = case.metadata.get("pipeline_provenance") or {}
    return ProvenanceView(
        case_id=case.case_id,
        artifact_ids=[a.artifact_id for a in artifacts],
        source_ids=sorted({a.produced_by for a in artifacts}
                          | set(pipeline_prov.get("source_ids") or [])),
        model_versions=dict(pipeline_prov.get("model_versions") or {}),
        processing_versions=dict(pipeline_prov.get("processing_versions") or {}),
        manifest_artifact_id=manifest.artifact_id if manifest else None,
        generated_at=generated_at,
    )


def _recommendation(case: Case, validity: SectionEnvelope[ValidityGateResult]) -> OperationalDecisionState:
    """
    `OperationalDecisionState` — a derived, lossy VIEW over `validity`, never
    a second gate. See `varuna_abhiyan.decision_state.
    derive_operational_decision_state` and `OperationalDecisionState`'s own
    docstring for the full mapping and rationale.

    `validity_stage_failed` must come from the pipeline's own raw
    `StageStatus` (via `_section_payload`), NOT from `validity.status`
    (`ProducerStatus`): this module deliberately maps a RESTRICTED gate to
    `ProducerStatus.BLOCKED` on the `validity` SectionEnvelope (a
    successful, restrictive evaluation — see `_validity_section`), which is
    a completely different claim from `StageStatus.BLOCKED` (the gate
    crashed). Reading `validity.status` here would silently relabel every
    RESTRICTED case as a pipeline failure.
    """
    from varuna_abhiyan.decision_state import derive_operational_decision_state

    payload = _section_payload(case, "validity")
    stage_status = (payload or {}).get("status")
    return derive_operational_decision_state(
        validity.value, validity_stage_failed=(stage_status == "blocked"),
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

    # Explicit starting-point contract (see varuna_geospatial.starting_point).
    # Resolved from the SAME already-projected section values the rest of this
    # view uses, so it can never disagree with what the operator is shown.
    from varuna_geospatial.starting_point import resolve_starting_point

    starting_point = resolve_starting_point(
        detection.value if detection.status is ProducerStatus.PRODUCED else None,
        origin.value if origin.status is ProducerStatus.PRODUCED else None,
        detection_evidence_mode=detection.evidence_mode,
        origin_evidence_mode=origin.evidence_mode,
    )

    return OperatorCase(
        case_id=case.case_id,
        generated_at=generated_at,
        system_status=SystemStatusView(
            case_status=case.status.value,
            scientific_status=case.scientific_status.value,
            error=case.error,
            # None for a case produced by the legacy CaseWorkflow path,
            # which never writes this key. A real value for a case produced
            # by GoldenCaseWorkflow, which writes it every _finalize() call.
            # See ADR-0012.
            engine_mode=case.metadata.get("engine_mode"),
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
        starting_point=starting_point,
        recommendation=_recommendation(case, validity),
        evidence=_evidence_health(observation, detection, origin, attribution, ais),
        provenance=_provenance(case, workflow, generated_at),
    )
