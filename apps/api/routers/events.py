"""
VARUNA GRID — Events Router.
"""
from fastapi import APIRouter, Depends
from typing import Optional

from varuna_domain.case_workflow import CaseWorkflow
from apps.api.dependencies import get_workflow
from apps.api.schemas import EventsListResponse

router = APIRouter(prefix="/v1/events", tags=["events"])

@router.get("", response_model=EventsListResponse)
def list_events(case_id: Optional[str] = None, workflow: CaseWorkflow = Depends(get_workflow)):
    if case_id:
        events = workflow.event_spine.list_by_case(case_id)
    else:
        events = workflow.event_spine.list_all()
    return {
        "count": len(events),
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "case_id": e.case_id,
                "actor": e.actor,
                "timestamp": e.timestamp,
                "payload": e.payload,
            }
            for e in events
        ],
    }
