"""
VARUNA GRID — API Schemas.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from varuna_contracts.schemas import GeoPoint


class CreateCaseRequest(BaseModel):
    """Every field beyond `case_id` is optional (Phase 3) — a bare `{}` POST
    still creates a case with zero detail, exactly as before; an operator who
    has more information can supply as much or as little of it as they have.
    Nothing here is inferred or defaulted from a case_id — a field left out
    stays genuinely absent in `case.metadata`, never silently filled in."""
    case_id: Optional[str] = None
    reported_by: Optional[str] = Field(
        None, description="Display name of the reporting operator; defaults to the authenticated principal if omitted.")
    initial_location: Optional[GeoPoint] = Field(
        None, description="Rough position if the operator has one at intake time.")
    observation_source: Optional[str] = Field(
        None, description='e.g. "Coast Guard patrol report", "Sentinel-1 tasking", "public tip-off".')
    priority: Optional[str] = Field(
        None, description="Operator's initial read of urgency — a free-text hint, not a computed severity.")
    notes: Optional[str] = Field(
        None, description="Free text, stored verbatim, never parsed or acted on automatically.")

class IngestRequest(BaseModel):
    use_fixture: str = "case_0001"

class ReconstructRequest(BaseModel):
    seed: int = 42

class AttributeRequest(BaseModel):
    latent_prior: float = 0.5

class CaseResponse(BaseModel):
    case_id: str
    status: str
    scientific_status: str
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    n_artifacts: int
    n_events: int

class EventResponse(BaseModel):
    event_id: str
    event_type: str
    case_id: str
    actor: str
    timestamp: datetime
    payload: Dict[str, Any]

class EventsListResponse(BaseModel):
    count: int
    events: List[EventResponse]

class PhiResponse(BaseModel):
    phi_id: str
    grid_shape: List[int]
    n_particles: int
    n_ensemble: int
    entropy: float
    concentration: float
    effective_support_km2: float

class CandidateResponse(BaseModel):
    rank: int
    mmsi: str
    posterior: float

class AttributionResponse(BaseModel):
    case_id: str
    decision_state: str
    latent_probability: float
    latent_finding: str
    top_posterior: float
    distinguishability: float
    posterior_entropy: float
    n_candidates: int
    scientific_status: str
    candidates: List[CandidateResponse]
