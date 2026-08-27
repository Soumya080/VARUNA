from enum import Enum
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from varuna_contracts.schemas import VesselType, VesselTrack, AISPoint, AISGap
from varuna_data_eng.schemas.provenance import DataProvenance

class GapClass(str, Enum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"
    VERY_LONG = "VERY_LONG"

class CleaningAction(BaseModel):
    action_type: str
    description: str
    timestamp: datetime

    model_config = ConfigDict(extra="forbid")

class AISGapRecord(BaseModel):
    start: datetime
    end: datetime
    duration_minutes: float
    distance_km: float
    gap_class: GapClass
    interpolated: bool
    interpolation_method: Optional[str] = None
    is_observable: bool

    model_config = ConfigDict(extra="forbid")

class RawAISPoint(BaseModel):
    mmsi: str
    timestamp: datetime
    lon: float
    lat: float
    sog_knots: Optional[float] = None
    cog_deg: Optional[float] = None
    heading_deg: Optional[float] = None
    vessel_type_code: Optional[int] = None
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    draught_m: Optional[float] = None
    destination: Optional[str] = None
    nav_status: Optional[int] = None
    source: str
    provenance: DataProvenance

    model_config = ConfigDict(extra="forbid")

class RawAISTrack(BaseModel):
    track_id: str
    mmsi: str
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    vessel_type: VesselType
    points: List[RawAISPoint]
    gaps: List[AISGapRecord]
    quality_flags: List[str]
    cleaning_log: List[CleaningAction]
    provenance: DataProvenance

    model_config = ConfigDict(extra="forbid")

def raw_to_locked(raw: RawAISTrack) -> VesselTrack:
    """Mapper from raw engineering track to locked operational track."""
    locked_points = []
    for pt in raw.points:
        locked_points.append(AISPoint(
            timestamp=pt.timestamp,
            lon=pt.lon,
            lat=pt.lat,
            sog_knots=pt.sog_knots,
            cog_deg=pt.cog_deg,
            heading_deg=pt.heading_deg,
            interpolated=False
        ))
    
    locked_gaps = []
    for gap in raw.gaps:
        locked_gaps.append(AISGap(
            start=gap.start,
            end=gap.end,
            duration_minutes=gap.duration_minutes,
            distance_km=gap.distance_km
        ))
    
    return VesselTrack(
        mmsi=raw.mmsi,
        imo=raw.imo,
        name=raw.vessel_name,
        vessel_type=raw.vessel_type,
        points=locked_points,
        gaps=locked_gaps
    )
