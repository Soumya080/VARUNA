"""
VARUNA GRID — Cases Router.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from varuna_domain.case_workflow import CaseWorkflow
from tests.fixtures.case_0001 import generate_case_0001
from apps.api.dependencies import get_workflow, get_case_resolver
from apps.api.config import settings
import logging

logger = logging.getLogger(__name__)
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

@router.post("", response_model=Dict[str, Any])
def create_case(
    req: CreateCaseRequest, workflow: CaseWorkflow = Depends(get_workflow),
    principal: Principal = Depends(get_principal),
):
    """Every field beyond `case_id` is optional (Phase 3) — `{}` still
    creates a case with zero detail. `reported_by` defaults to the
    authenticated principal when the caller doesn't supply one, since a case
    always has a real reporter even when the form was skipped."""
    authorize(principal, Permission.CREATE_CASE, "create_case")
    if workflow.cases.get(req.case_id):
        raise HTTPException(409, f"Case {req.case_id} already exists")

    metadata = {
        "reported_by": req.reported_by or principal.principal_id,
        "initial_location": req.initial_location.model_dump() if req.initial_location else None,
        "observation_source": req.observation_source,
        "priority": req.priority,
        "notes": req.notes,
    }
    case = workflow.create_case(req.case_id, metadata=metadata)
    return {
        "case_id": case.case_id,
        "status": case.status.value,
        "metadata": case.metadata,
    }

@router.get("", response_model=Dict[str, Any])
def list_cases(resolver=Depends(get_case_resolver)):
    """Every case a UI should be able to see, from every repository — via
    `case_resolver.list_all()`, the SAME resolution logic every per-case
    route below uses. This used to be a separate, hand-rolled merge that
    silently disagreed with the per-case routes (B1) — a case flagged
    `has_operator_view: true` here could still 404 on
    `/v1/cases/{id}/operator-view`. Listing and detail now share one source
    of truth, so that class of disagreement is structurally impossible.

    Also enriched: status alone is not enough to triage from. Each row
    carries its validity state, recommendation, and alert/mission counts,
    all read from state that already exists — nothing is computed here.
    """
    from apps.api.dependencies import get_alert_lifecycle_service, get_mission_service

    alerts_svc = get_alert_lifecycle_service()
    missions_svc = get_mission_service()

    items = []
    try:
        resolved = resolver.list_all()
    except Exception:
        logger.exception("list_cases: case resolution failed")
        return {"items": [], "total": 0, "degraded": True, "degraded_reason": "case store enumeration failed"}

    for r in resolved:
        cid = r.case.case_id
        oc = r.composed
        validity = None
        recommendation = None
        if oc is not None:
            v = getattr(getattr(oc, "validity", None), "value", None)
            st = getattr(v, "state", None) if v is not None else None
            validity = getattr(st, "value", st)
            recommendation = getattr(getattr(oc, "recommendation", None), "value", None)
        items.append({
            "case_id": cid,
            "status": r.case.status.value,
            "created_at": r.case.created_at,
            "source": r.source,
            "engine_mode": (r.case.metadata or {}).get("engine_mode"),
            "validity_state": validity,
            "recommendation": recommendation,
            "n_alerts": len(alerts_svc.list_by_case(cid)),
            "n_missions": len(missions_svc.list_by_case(cid)),
            "has_operator_view": r.has_operator_view,
        })

    return {"items": items, "total": len(items)}

@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str, resolver=Depends(get_case_resolver)):
    resolved = resolver.resolve(case_id)
    if not resolved:
        raise CaseNotFoundError(case_id)
    case, workflow = resolved.case, resolved.workflow
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
def get_phi(case_id: str, resolver=Depends(get_case_resolver)):
    resolved = resolver.resolve(case_id)
    case = resolved.case if resolved else None
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
def get_attribution(case_id: str, resolver=Depends(get_case_resolver)):
    resolved = resolver.resolve(case_id)
    case = resolved.case if resolved else None
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
def get_validity(case_id: str, resolver=Depends(get_case_resolver)):
    resolved = resolver.resolve(case_id)
    case = resolved.case if resolved else None
    if not case or "gate_result" not in case.metadata:
        raise HTTPException(404, "Validity not available")
    return case.metadata["gate_result"]

@router.get("/{case_id}/operator-view", response_model=OperatorCase)
def get_operator_view(case_id: str, resolver=Depends(get_case_resolver)):
    """
    Read-only canonical operator case projection (OPERATOR_CASE_SCHEMA_VERSION).
    See docs/api/OPERATOR_CASE_CONTRACT_V1.md. Serializes real backend state
    only — never computes, infers, or overrides it.

    B1 fix: this used to resolve `case_id` against the legacy `CaseWorkflow`
    only, so every replay case (`GoldenCaseWorkflow` + `_COMPOSED_CACHE`)
    404'd here regardless of what `/v1/cases` advertised. Now resolved the
    same way the list route resolves it. When an already-composed
    `OperatorCase` exists (every replay case has one, built by
    `run_operational_loop` — including alerts/missions this rebuild path
    wouldn't reproduce), it is returned directly rather than rebuilt, since
    it is both cheaper and strictly richer than reconstructing from
    `.metadata`.
    """
    resolved = resolver.resolve(case_id)
    if not resolved:
        raise CaseNotFoundError(case_id)
    if resolved.composed is not None:
        return resolved.composed
    return build_operator_case(resolved.case, resolved.workflow)

@router.get("/{case_id}/artifacts")
def get_artifacts(case_id: str, resolver=Depends(get_case_resolver)):
    resolved = resolver.resolve(case_id)
    if not resolved:
        raise CaseNotFoundError(case_id)
    artifacts = resolved.workflow.praman.list_by_case(case_id)
    return {
        "items": [
            {"id": a.artifact_id, "type": a.artifact_type, "produced_by": a.produced_by, "created_at": a.created_at}
            for a in artifacts
        ]
    }
