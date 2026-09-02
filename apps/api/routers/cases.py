"""
VARUNA GRID — Cases Router.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from varuna_domain.case_workflow import CaseWorkflow
from tests.fixtures.case_0001 import generate_case_0001
from apps.api.dependencies import get_workflow
from apps.api.config import settings
from apps.api.schemas import (
    CreateCaseRequest, CaseResponse, IngestRequest, ReconstructRequest,
    AttributeRequest, PhiResponse, AttributionResponse
)
from apps.api.errors import CaseNotFoundError
from apps.api.operator_case_view import build_operator_case
from apps.api.security import get_principal
from varuna_contracts.operator_case import OperatorCase
from varuna_infra.authorization import Principal, authorize
from varuna_infra.rbac import Permission

# Explicit allowlist of fixture generators the ingest endpoint may invoke.
# Prior code did `importlib.import_module(f"tests.fixtures.{req.use_fixture}")`
# with `req.use_fixture` taken directly from the request body — production
# code performing an attacker-influenced dynamic import of any module under
# `tests.fixtures`. This closes that: only names in this table can ever be
# loaded, and the body value is a lookup key, never a module path.
_FIXTURE_REGISTRY = {
    "case_0001": generate_case_0001,
}

router = APIRouter(prefix="/v1/cases", tags=["cases"])

from fastapi import HTTPException

@router.post("", response_model=Dict[str, str])
def create_case(
    req: CreateCaseRequest, workflow: CaseWorkflow = Depends(get_workflow),
    principal: Principal = Depends(get_principal),
):
    authorize(principal, Permission.CREATE_CASE, "create_case")
    if workflow.cases.get(req.case_id):
        raise HTTPException(409, f"Case {req.case_id} already exists")
    case = workflow.create_case(req.case_id)
    return {"case_id": case.case_id, "status": case.status.value}

@router.get("", response_model=Dict[str, Any])
def list_cases(workflow: CaseWorkflow = Depends(get_workflow)):
    cases = workflow.cases.list_all()
    return {
        "items": [
            {"case_id": c.case_id, "status": c.status.value, "created_at": c.created_at}
            for c in cases
        ],
        "total": len(cases),
    }

@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, workflow: CaseWorkflow = Depends(get_workflow)):
    case = workflow.cases.get(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    return {
        "case_id": case.case_id,
        "status": case.status.value,
        "scientific_status": settings.scientific_status,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "error": case.error,
        "n_artifacts": len(workflow.praman.list_by_case(case_id)),
        "n_events": len(workflow.event_spine.list_by_case(case_id)),
    }

@router.post("/{case_id}/ingest")
def ingest(
    case_id: str, req: IngestRequest, workflow: CaseWorkflow = Depends(get_workflow),
    principal: Principal = Depends(get_principal),
):
    authorize(principal, Permission.RUN_CASE_STAGE, "ingest", subject_id=case_id)
    case = workflow.cases.get(case_id)
    if not case:
        raise CaseNotFoundError(case_id)

    fixture_gen = _FIXTURE_REGISTRY.get(req.use_fixture)
    if fixture_gen is None:
        raise HTTPException(400, f"Unknown fixture: {req.use_fixture}")
    fixture = fixture_gen()

    case, guard = workflow.ingest(
        case, fixture["slick_lons"], fixture["slick_lats"],
        fixture["tracks"], fixture["obs_time_hours"],
    )
    return {
        "case_id": case_id,
        "guard_verdict": guard.verdict.value,
        "status": case.status.value,
    }

@router.post("/{case_id}/reconstruct")
def reconstruct(
    case_id: str, req: ReconstructRequest, workflow: CaseWorkflow = Depends(get_workflow),
    principal: Principal = Depends(get_principal),
):
    authorize(principal, Permission.RUN_CASE_STAGE, "reconstruct", subject_id=case_id)
    case = workflow.cases.get(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    result = workflow.reconstruct(case, seed=req.seed)
    return {"case_id": case_id, **result}

@router.post("/{case_id}/attribute")
def attribute(
    case_id: str, req: AttributeRequest, workflow: CaseWorkflow = Depends(get_workflow),
    principal: Principal = Depends(get_principal),
):
    authorize(principal, Permission.RUN_CASE_STAGE, "attribute", subject_id=case_id)
    case = workflow.cases.get(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    result = workflow.attribute(case, latent_prior=req.latent_prior)
    return {"case_id": case_id, **result}

@router.get("/{case_id}/phi", response_model=PhiResponse)
def get_phi(case_id: str, workflow: CaseWorkflow = Depends(get_workflow)):
    case = workflow.cases.get(case_id)
    if not case or "phi" not in case.metadata:
        raise HTTPException(404, "PhiField not available")
    
    from varuna_contracts.phi import PhiField
    phi = PhiField.model_validate(case.metadata["phi"])
    return {
        "phi_id": phi.phi_id,
        "grid_shape": phi.grid_shape,
        "n_particles": phi.n_particles,
        "n_ensemble": phi.n_ensemble,
        "entropy": phi.diagnostics.entropy,
        "concentration": phi.diagnostics.concentration,
        "effective_support_km2": phi.diagnostics.effective_support_km2,
    }

@router.get("/{case_id}/attribution", response_model=AttributionResponse)
def get_attribution(case_id: str, workflow: CaseWorkflow = Depends(get_workflow)):
    case = workflow.cases.get(case_id)
    if not case or "attribution" not in case.metadata:
        raise HTTPException(404, "Attribution not available")
    
    from varuna_contracts.decision import AttributionResultV2
    attr = AttributionResultV2.model_validate(case.metadata["attribution"])
    return {
        "case_id": case_id,
        "decision_state": attr.decision_state.value,
        "latent_probability": attr.latent_probability,
        "latent_finding": attr.latent_finding.value,
        "top_posterior": attr.top_posterior,
        "distinguishability": attr.distinguishability,
        "posterior_entropy": attr.posterior_entropy,
        "n_candidates": len(attr.candidates),
        "scientific_status": settings.scientific_status,
        "candidates": [
            {"rank": c.rank, "mmsi": c.mmsi, "posterior": c.posterior}
            for c in attr.candidates[:5]
        ],
    }

@router.get("/{case_id}/validity")
def get_validity(case_id: str, workflow: CaseWorkflow = Depends(get_workflow)):
    case = workflow.cases.get(case_id)
    if not case or "gate_result" not in case.metadata:
        raise HTTPException(404, "Validity not available")
    return case.metadata["gate_result"]

@router.get("/{case_id}/operator-view", response_model=OperatorCase)
def get_operator_view(case_id: str, workflow: CaseWorkflow = Depends(get_workflow)):
    """
    Read-only canonical operator case projection (OPERATOR_CASE_SCHEMA_VERSION).
    See docs/api/OPERATOR_CASE_CONTRACT_V1.md. Serializes real backend state
    only — never computes, infers, or overrides it.
    """
    case = workflow.cases.get(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    return build_operator_case(case, workflow)

@router.get("/{case_id}/artifacts")
def get_artifacts(case_id: str, workflow: CaseWorkflow = Depends(get_workflow)):
    case = workflow.cases.get(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    artifacts = workflow.praman.list_by_case(case_id)
    return {
        "items": [
            {"id": a.artifact_id, "type": a.artifact_type, "produced_by": a.produced_by, "created_at": a.created_at}
            for a in artifacts
        ]
    }
