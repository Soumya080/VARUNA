from fastapi import APIRouter, Depends
from apps.api.config import settings
from apps.api.dependencies import get_workflow, get_mission_service, get_alert_service

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


@router.get("/marine-context")
def marine_context():
    """Phase 9 (Tier 1) — real per-source data freshness, honestly labelled.

    Answers "how fresh is this marine data, actually" from real file
    metadata on disk. Deliberately NOT a live feed: ERA5/CMEMS/AIS are all
    confirmed real-but-archival (pre-fetched local files, not a live remote
    fetch — see packages/varuna_source_adapters/{era5,copernicus_marine}.py's
    own docstrings). Never rounds a stale file up to "live" or "real-time".
    """
    from varuna_source_adapters.marine_freshness import marine_context_report

    report = marine_context_report()
    return {
        source_id: {
            "tier": f.tier,
            "found": f.found,
            "file_path": f.file_path,
            "data_as_of": f.data_as_of.isoformat() if f.data_as_of else None,
            "age_days": f.age_days,
            "label": f.honest_label,
        }
        for source_id, f in report.items()
    }

@router.get("/summary")
def dashboard_summary(
    workflow = Depends(get_workflow),
    mission_svc = Depends(get_mission_service),
    alert_svc = Depends(get_alert_service),
):
    cases = workflow.cases.list_all()
    active_missions = mission_svc.list_active()
    alert_log = alert_svc.get_delivery_log()
    return {
        "total_cases": len(cases),
        "active_cases": len([c for c in cases if c.status.value not in ("completed", "failed", "quarantined")]),
        "active_missions": len(active_missions),
        "total_alerts_sent": len([a for a in alert_log if a.status == "sent"]),
        "scientific_status": settings.scientific_status,
    }
