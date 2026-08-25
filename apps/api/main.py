"""
VARUNA GRID — FastAPI Application.

Minimum end-to-end routes for CASE-0001 vertical slice.
No PostgreSQL, Redis, or MinIO required.
"""
import datetime as _dt
if not hasattr(_dt, "UTC"):
    _dt.UTC = _dt.timezone.utc
import enum as _enum
if not hasattr(_enum, "StrEnum"):
    class _StrEnum(str, _enum.Enum): pass
    _enum.StrEnum = _StrEnum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import numpy as np

from varuna_domain.case_workflow import CaseWorkflow
from tests.fixtures.case_0001 import generate_case_0001

app = FastAPI(
    title="VARUNA GRID v2 API",
    description="Oil spill attribution — EXPERIMENTAL, M2.1 provisional results",
    version="2.0.0-experimental",
)

# Shared in-memory workflow instance
_workflow = CaseWorkflow()


class CreateCaseRequest(BaseModel):
    case_id: Optional[str] = None


class IngestRequest(BaseModel):
    use_fixture: str = "case_0001"


class ReconstructRequest(BaseModel):
    seed: int = 42


class AttributeRequest(BaseModel):
    latent_prior: float = 0.5


@app.post("/v1/cases")
def create_case(req: CreateCaseRequest):
    case = _workflow.create_case(req.case_id)
    return {"case_id": case.case_id, "status": case.status.value}


@app.get("/v1/cases/{case_id}")
def get_case(case_id: str):
    case = _workflow.cases.get(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    return {
        "case_id": case.case_id,
        "status": case.status.value,
        "scientific_status": case.scientific_status.value,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "error": case.error,
        "n_artifacts": len(_workflow.praman.list_by_case(case_id)),
        "n_events": len(_workflow.event_spine.list_by_case(case_id)),
    }


@app.post("/v1/cases/{case_id}/ingest")
def ingest(case_id: str, req: IngestRequest):
    case = _workflow.cases.get(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    fixture = generate_case_0001()
    case, guard = _workflow.ingest(
        case, fixture["slick_lons"], fixture["slick_lats"],
        fixture["tracks"], fixture["obs_time_hours"],
    )
    return {
        "case_id": case_id,
        "guard_verdict": guard.verdict.value,
        "status": case.status.value,
    }


@app.post("/v1/cases/{case_id}/reconstruct")
def reconstruct(case_id: str, req: ReconstructRequest):
    case = _workflow.cases.get(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    result = _workflow.reconstruct(case, seed=req.seed)
    return {"case_id": case_id, **result}


@app.post("/v1/cases/{case_id}/attribute")
def attribute(case_id: str, req: AttributeRequest):
    case = _workflow.cases.get(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    result = _workflow.attribute(case, latent_prior=req.latent_prior)
    return {"case_id": case_id, **result}


@app.get("/v1/cases/{case_id}/phi")
def get_phi(case_id: str):
    case = _workflow.cases.get(case_id)
    if not case or not hasattr(case, "_phi"):
        raise HTTPException(404, "PhiField not available")
    phi = case._phi
    return {
        "phi_id": phi.phi_id,
        "grid_shape": phi.grid_shape,
        "n_particles": phi.n_particles,
        "n_ensemble": phi.n_ensemble,
        "entropy": phi.diagnostics.entropy,
        "concentration": phi.diagnostics.concentration,
        "effective_support_km2": phi.diagnostics.effective_support_km2,
    }


@app.get("/v1/cases/{case_id}/attribution")
def get_attribution(case_id: str):
    case = _workflow.cases.get(case_id)
    if not case or not hasattr(case, "_attribution"):
        raise HTTPException(404, "Attribution not available")
    attr = case._attribution
    return {
        "case_id": case_id,
        "decision_state": attr.decision_state.value,
        "latent_probability": attr.latent_probability,
        "latent_finding": attr.latent_finding.value,
        "top_posterior": attr.top_posterior,
        "distinguishability": attr.distinguishability,
        "posterior_entropy": attr.posterior_entropy,
        "n_candidates": len(attr.candidates),
        "scientific_status": "experimental",
        "candidates": [
            {"rank": c.rank, "mmsi": c.mmsi, "posterior": c.posterior}
            for c in attr.candidates[:5]
        ],
    }


@app.get("/v1/events")
def list_events(case_id: Optional[str] = None):
    if case_id:
        events = _workflow.event_spine.list_by_case(case_id)
    else:
        events = _workflow.event_spine.list_all()
    return {
        "count": len(events),
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "case_id": e.case_id,
                "actor": e.actor,
                "timestamp": e.timestamp.isoformat(),
                "payload": e.payload,
            }
            for e in events
        ],
    }
