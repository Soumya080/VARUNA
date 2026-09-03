"""VARUNA — incident report endpoint (Workstream A, Phase 12)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from apps.api.dependencies import (
    get_alert_lifecycle_service, get_golden_case_workflow, get_mission_service,
    get_replay_smriti_store,
)
from apps.api.routers.replay import _COMPOSED_CACHE

router = APIRouter(prefix="/v1/cases", tags=["reports"])


@router.get("/{case_id}/report")
def case_report(
    case_id: str,
    alerts_svc=Depends(get_alert_lifecycle_service),
    missions=Depends(get_mission_service),
    smriti=Depends(get_replay_smriti_store),
    workflow=Depends(get_golden_case_workflow),
):
    """Generate the incident PDF for a case that has already been run.

    Reads the SAME composed OperatorCase the cockpit shows (from the replay
    composed-response cache) rather than recomputing, so the report and the
    screen can never disagree. A case that has not been run yet is a 404 —
    the report is never generated from a fabricated case.
    """
    from varuna_alerts.channel_orchestrator import ChannelOrchestrator

    # This import is lazy so a missing reportlab cannot break API startup —
    # but it also sat outside the try/except below, so an absent dependency
    # surfaced as an unexplained 500. Name the missing package instead.
    try:
        from varuna_integration.incident_report import build_incident_report
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=("PDF reporting is unavailable: the 'reportlab' package is not "
                    f"installed in this environment ({exc}). Install the project "
                    "dependencies with `pip install -e .` from the repository root."),
        ) from exc

    operator_case = None
    for composed in _COMPOSED_CACHE.values():
        if getattr(composed, "case_id", None) == case_id:
            operator_case = composed
            break
    if operator_case is None:
        raise HTTPException(
            status_code=404,
            detail=(f"No composed case {case_id!r} is available. Run the case first "
                    "(GET /v1/replay/{fixture}) — a report is never generated from a "
                    "case that has not been executed."),
        )

    alerts = alerts_svc.list_by_case(case_id)

    mission_audit: list[dict] = []
    for m in missions.list_by_case(case_id):
        mission_audit.extend(
            e.model_dump(mode="json") for e in missions.audit_log.for_subject(m.mission_id))

    smriti_hits: list[dict] = []
    try:
        mem = smriti.get(case_id)
        if mem is not None:
            retrieval = smriti.retrieve_similar_cases(mem, limit=5)
            for h in getattr(retrieval, "hits", []) or []:
                smriti_hits.append({
                    "case_id": getattr(getattr(h, "memory", None), "case_id", None),
                    "score": round(getattr(h, "score", 0.0), 3),
                })
    except Exception:
        smriti_hits = []

    try:
        pdf = build_incident_report(
            operator_case, alerts=alerts, mission_audit=mission_audit,
            smriti_hits=smriti_hits,
            channel_report=ChannelOrchestrator.channel_report(),
            run_id=None,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"report generation failed: {type(exc).__name__}: {exc}") from exc

    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="VARUNA-incident-{case_id}.pdf"'},
    )


@router.get("/{case_id}/operational-summary")
def operational_summary(case_id: str, alerts_svc=Depends(get_alert_lifecycle_service),
                        missions=Depends(get_mission_service)):
    """Compact operational state for the cockpit: alerts (with routing and
    delivery), mission, and the honest per-channel configuration report."""
    from varuna_alerts.channel_orchestrator import ChannelOrchestrator

    return {
        "case_id": case_id,
        "alerts": [a.model_dump(mode="json") for a in alerts_svc.list_by_case(case_id)],
        "missions": [m.model_dump(mode="json") for m in missions.list_by_case(case_id)],
        "channels": ChannelOrchestrator.channel_report(),
    }
