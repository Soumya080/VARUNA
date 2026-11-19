from fastapi import APIRouter, Depends
from apps.api.config import settings
from apps.api.dependencies import get_case_resolver, get_mission_service, get_alert_store

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
    resolver = Depends(get_case_resolver),
    mission_svc = Depends(get_mission_service),
    alert_store = Depends(get_alert_store),
):
    """B2 fix (3 independent bugs, all corrected here):

    1. Cases now come from `case_resolver.list_all()` — the same union
       every other route uses — instead of only the legacy `CaseWorkflow`
       store, which is why this used to report `total_cases: 1` while 6
       cases existed.
    2. "Active" is now `not status.is_terminal` (see
       `varuna_domain.entities.CaseStatus.is_terminal`), not a hardcoded
       `("completed", "failed", "quarantined")` literal that never matched
       the golden engine's real terminal values (`complete`, `blocked`,
       `unavailable`, `ood`).
    3. Alerts sent now comes from the real alert store (`get_alert_store()`
       — the ONE store every delivered alert actually lands in) rather than
       a freshly-constructed `AlertService` whose `_delivery_log` is empty
       on every call because nothing ever sends through it — that was a
       hardcoded zero by construction, not a measurement. Delivery status
       is read from each alert's `deliveries` (raw `DeliveryResult` dicts,
       status values from `varuna_alerts.channel_orchestrator.DeliveryStatus`,
       UPPERCASE) rather than compared against a lowercase literal that
       could never match.
    """
    resolved = resolver.list_all()
    cases = [r.case for r in resolved]
    active_missions = mission_svc.list_active()

    delivered_statuses = {"SENT", "DELIVERED"}
    total_alerts_sent = sum(
        1
        for alert in alert_store.all()
        for delivery in alert.deliveries
        if delivery.get("status") in delivered_statuses
    )

    return {
        "total_cases": len(cases),
        "active_cases": len([c for c in cases if not c.status.is_terminal]),
        "active_missions": len(active_missions),
        "total_alerts_sent": total_alerts_sent,
        "scientific_status": settings.scientific_status,
    }
