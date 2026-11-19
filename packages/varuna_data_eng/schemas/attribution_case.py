from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from varuna_contracts.schemas import GeoPoint, VesselTrack
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.oil_mask import OilMask
from varuna_data_eng.schemas.forcing import ForcingCube
from varuna_data_eng.schemas.provenance import DataProvenance

class AgePrior(BaseModel):
    mean_hours: float
    std_hours: float
    source: str

    model_config = ConfigDict(extra="forbid")

class AttributionCaseInput(BaseModel):
    """What inference receives. No truth fields."""
    slick_observation: CanonicalSAR
    slick_mask: OilMask
    observation_time: datetime
    age_prior: AgePrior
    ais_tracks: List[VesselTrack]
    forcing: ForcingCube
    candidate_vessels: List[str]

    model_config = ConfigDict(extra="forbid")

class AttributionCaseTruth(BaseModel):
    """Evaluation-only. Never imported by inference modules."""
    true_source_mmsi: Optional[str] = None
    true_release_point: Optional[GeoPoint] = None
    true_release_time: Optional[datetime] = None
    true_slick_age_hours: Optional[float] = None
    generation_method: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class CaseMetadata(BaseModel):
    case_version: str
    created_at: datetime
    provenance: DataProvenance

    model_config = ConfigDict(extra="forbid")

class AttributionCase(BaseModel):
    case_id: str
    input: AttributionCaseInput
    truth: Optional[AttributionCaseTruth] = None
    metadata: CaseMetadata

    model_config = ConfigDict(extra="forbid")
