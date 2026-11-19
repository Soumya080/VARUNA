"""
VARUNA — SMRITI operator-feedback endpoint (Phase 7).

Captures whether a retrieved similar case was actually useful to the
operator. Feeds the adaptive reweighting mechanism in
`varuna_smriti.feedback` — never touches live case evidence, never alters a
validity verdict; `MemoryRetrieval.advisory_only` stays `True` regardless.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.dependencies import get_smriti_feedback_store, get_replay_smriti_store
from apps.api.security import get_principal
from varuna_infra.authorization import Principal
from varuna_smriti.feedback import MemoryFeedback, SmritiFeedbackStore

router = APIRouter(prefix="/v1/cases", tags=["smriti"])


class MemoryFeedbackRequest(BaseModel):
    retrieved_case_id: str = Field(..., min_length=1)
    useful: bool
    similarity_at_retrieval: float = 0.0
    # Captured verbatim from the memory_hit the operator is judging — see
    # `OperatorCase.intelligence.memory_hits[i].components`, which the
    # `_consult_memory()` action already includes for exactly this purpose.
    components_at_retrieval: dict[str, float] = Field(default_factory=dict)


@router.post("/{case_id}/memory-feedback")
def submit_memory_feedback(
    case_id: str,
    body: MemoryFeedbackRequest,
    store: SmritiFeedbackStore = Depends(get_smriti_feedback_store),
    principal: Principal = Depends(get_principal),
):
    """Any authenticated principal may submit feedback — this is a lower-
    stakes action than any RBAC-gated mutation (it never changes case
    state), so no Permission is required beyond being a real, identified
    principal (never anonymous, so the audit trail is meaningful)."""
    if not body.retrieved_case_id.strip():
        raise HTTPException(status_code=422, detail="retrieved_case_id must not be blank")

    feedback = MemoryFeedback(
        query_case_id=case_id,
        retrieved_case_id=body.retrieved_case_id,
        similarity_at_retrieval=body.similarity_at_retrieval,
        components_at_retrieval=body.components_at_retrieval,
        useful=body.useful,
        recorded_by=principal.principal_id,
    )
    store.record(feedback)
    return feedback.model_dump(mode="json")


@router.get("/{case_id}/memory-feedback")
def list_memory_feedback_for_case(
    case_id: str,
    store: SmritiFeedbackStore = Depends(get_smriti_feedback_store),
):
    items = [f for f in store.all() if f.query_case_id == case_id]
    return {"items": [f.model_dump(mode="json") for f in items]}


@router.get("/{case_id}/memory-outcome")
def get_memory_outcome(
    case_id: str,
    smriti=Depends(get_replay_smriti_store),
):
    """Phase 6B (docs/product/HONESTY_LEDGER.md): the 5th Verification
    Ledger axis — has THIS case's own outcome ever been recorded in SMRITI
    (`CaseMemory.outcome`, e.g. "confirmed"/"not_found"/"unresolved")? This
    is distinct from `intelligence.memory_hits`, which surfaces OTHER
    similar past cases, not this case's own recorded outcome.
    """
    mem = smriti.get(case_id)
    if mem is None:
        return {"case_id": case_id, "recorded": False, "outcome": None}
    return {
        "case_id": case_id,
        "recorded": True,
        "outcome": mem.outcome,
        "recorded_at": mem.recorded_at.isoformat(),
        "updated_at": mem.updated_at.isoformat(),
    }
