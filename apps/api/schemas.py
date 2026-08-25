"""
VARUNA GRID — API Schemas.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class CreateCaseRequest(BaseModel):
    case_id: Optional[str] = None

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
