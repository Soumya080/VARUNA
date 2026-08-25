"""
VARUNA GRID — shared data contracts.

THE ONLY cross-subsystem dependency. If every subsystem produces and consumes
these types, integration is automatic. Do not duplicate these definitions.

Conventions:
  - All coordinates WGS84, (lon, lat), degrees.
  - All times timezone-aware UTC. Never naive datetimes.
  - All distances km, areas km^2, speeds knots (AIS) or m/s (forcing).
"""

from __future__ import annotations

from datetime import timezone, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "AISGap",
    "AISPoint",
    "AssetTasking",
    "AssetType",
    "AttributionResult",
    "BBox",
    "Case",
    "CaseStatus",
    "DarkVesselDetection",
    "EmissionPrior",
    "EvidenceManifest",
    "ForcingErrorLevel",
    "ForwardForecast",
    "GeoPoint",
    "LandfallPrediction",
    "LatentSourceScore",
    "LookAlikeType",
    "OfficerDecision",
    "PhiFieldMeta",
    "SearchBox",
    "SlickClass",
    "SlickDetection",
    "VerdictType",
    "VesselScore",
    "VesselTrack",
    "VesselType",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        ser_json_timedelta="float",
    )


# ───────────────────────── Enums ─────────────────────────

class SlickClass(StrEnum):
    OIL = "oil"
    LOOK_ALIKE = "look_alike"
    AMBIGUOUS = "ambiguous"


class LookAlikeType(StrEnum):
    LOW_WIND = "low_wind"
    ALGAL_BLOOM = "algal_bloom"
    RAIN_CELL = "rain_cell"
    SHIP_WAKE = "ship_wake"
    NATURAL_SEEP = "natural_seep"
    UNKNOWN = "unknown"


class VerdictType(StrEnum):
    """M10 output. INCONCLUSIVE is a first-class result, not an error."""
    VESSEL_ATTRIBUTED = "vessel_attributed"
    LATENT_SOURCE_DOMINANT = "latent_source_dominant"
    INCONCLUSIVE = "inconclusive"


class ForcingErrorLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VesselType(StrEnum):
    TANKER = "tanker"
    CARGO = "cargo"
    FISHING = "fishing"
    PASSENGER = "passenger"
    TUG = "tug"
    OTHER = "other"
    UNKNOWN = "unknown"


class AssetType(StrEnum):
    DORNIER = "dornier"
    OPV = "opv"
    STATION_BOAT = "station_boat"


class CaseStatus(StrEnum):
    DETECTED = "detected"
    BACKTRACKED = "backtracked"
    ATTRIBUTED = "attributed"
    FORECAST = "forecast"
    TASKED = "tasked"
    CLOSED = "closed"


class OfficerDecision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MARKED_INCONCLUSIVE = "marked_inconclusive"


# ───────────────────────── Geometry ─────────────────────────

class GeoPoint(_Base):
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


class BBox(_Base):
    min_lon: float = Field(..., ge=-180, le=180)
    min_lat: float = Field(..., ge=-90, le=90)
    max_lon: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)

    @model_validator(mode="after")
    def _ordered(self) -> BBox:
        if self.min_lon >= self.max_lon:
            raise ValueError("min_lon must be < max_lon")
        if self.min_lat >= self.max_lat:
            raise ValueError("min_lat must be < max_lat")
        return self

    @property
    def center(self) -> GeoPoint:
        return GeoPoint(lon=(self.min_lon + self.max_lon) / 2,
                        lat=(self.min_lat + self.max_lat) / 2)

    def contains(self, p: GeoPoint) -> bool:
        return (self.min_lon <= p.lon <= self.max_lon
                and self.min_lat <= p.lat <= self.max_lat)


# ───────────────────────── NETRA (M2, M3) ─────────────────────────

class SlickDetection(_Base):
    """NETRA output. One detected dark feature, classified."""
    slick_id: str
    scene_id: str
    observation_time: datetime

    classification: SlickClass
    confidence: float = Field(..., ge=0, le=1)
    look_alike_type: LookAlikeType | None = None

    mask_path: str                       # MinIO key or local path, uint8 GeoTIFF
    centroid: GeoPoint
    bbox: BBox

    # M3 morphometry
    area_km2: float = Field(..., ge=0)
    perimeter_km: float = Field(..., ge=0)
    elongation: float = Field(..., ge=0)          # major/minor axis ratio
    orientation_deg: float = Field(..., ge=-180, le=180)

    # M3 age PRIOR — a distribution, never a point estimate (Section 11)
    age_prior_mean_hours: float = Field(..., gt=0)
    age_prior_std_hours: float = Field(..., gt=0)

    mean_wind_speed_ms: float | None = Field(None, ge=0)
    netra_model_version: str = "unset"

    @field_validator("observation_time")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("observation_time must be timezone-aware UTC")
        return v.astimezone(timezone.utc)


# ───────────────────────── AIS (M6) ─────────────────────────

class AISPoint(_Base):
    timestamp: datetime
    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)
    sog_knots: float | None = Field(None, ge=0, le=60)
    cog_deg: float | None = Field(None, ge=0, lt=360)
    heading_deg: float | None = Field(None, ge=0, lt=360)
    interpolated: bool = False
    position_std_km: float = Field(0.0, ge=0)   # inflated across gaps, never silently


class AISGap(_Base):
    start: datetime
    end: datetime
    duration_minutes: float = Field(..., ge=0)
    distance_km: float = Field(..., ge=0)


class VesselTrack(_Base):
    """A cleaned, gap-annotated vessel trajectory. NYAYA scores these against Phi."""
    mmsi: str
    imo: str | None = None
    name: str | None = None
    vessel_type: VesselType = VesselType.UNKNOWN
    length_m: float | None = Field(None, gt=0)
    width_m: float | None = Field(None, gt=0)

    points: list[AISPoint] = Field(..., min_length=2)
    gaps: list[AISGap] = Field(default_factory=list)

    # Judge control (Demo Moment 3): set False to simulate transponder-off.
    transponder_active: bool = True

    @property
    def start_time(self) -> datetime:
        return self.points[0].timestamp

    @property
    def end_time(self) -> datetime:
        return self.points[-1].timestamp

    @property
    def n_points(self) -> int:
        return len(self.points)

    @property
    def total_gap_minutes(self) -> float:
        return sum(g.duration_minutes for g in self.gaps)

    @property
    def max_gap_minutes(self) -> float:
        return max((g.duration_minutes for g in self.gaps), default=0.0)


# ───────────────────────── PRATIVARTAN (M5) ─────────────────────────

class PhiFieldMeta(_Base):
    """
    Metadata for a Phi(x, y, t) origin probability field.

    The array itself lives at `data_path` as a .npz with EXACTLY these keys:
        phi            float32 (n_t, n_y, n_x)  normalised: sum(phi) == 1.0
        lon_edges      float64 (n_x + 1,)
        lat_edges      float64 (n_y + 1,)
        time_edges     float64 (n_t + 1,)       unix seconds UTC
        particle_count int32   (n_t,)           members contributing per time bin

    3-D histogram, NOT a KDE. KDE was 40x slower and leaked memory in the
    go/no-go harness. Histogram is exact, fast, and serialises trivially to
    the frontend HeatmapLayer.
    """
    phi_id: str
    slick_id: str
    data_path: str
    bbox: BBox

    n_particles: int = Field(..., gt=0)     # seeded per ensemble member
    n_ensemble: int = Field(..., gt=0)      # M perturbed forcing realisations
    backward_duration_hours: float = Field(..., gt=0)
    dt_seconds: float = Field(..., gt=0)

    grid_shape: tuple[int, int, int]        # (n_t, n_y, n_x)
    lon_resolution_deg: float = Field(..., gt=0)
    lat_resolution_deg: float = Field(..., gt=0)
    time_resolution_hours: float = Field(..., gt=0)

    forcing_current_source: str             # e.g. "CMEMS GLOBAL_MULTIYEAR_PHY_001_030"
    forcing_wind_source: str                # e.g. "ERA5 10m u/v"
    forcing_error_level: ForcingErrorLevel = ForcingErrorLevel.MEDIUM

    # Diagnostics — drive the INCONCLUSIVE decision in M10.
    effective_area_km2: float = Field(..., ge=0)   # 90% mass containing area
    spatial_entropy: float = Field(..., ge=0)

    engine_version: str = "unset"
    created_at: datetime = Field(default_factory=_utcnow)


# ───────────────────────── NYAYA (M7, M8, M9, M10) ─────────────────────────

class EmissionPrior(_Base):
    """M8. Behavioural weight pi_k. Publish these weights — do not hide them."""
    gap_score: float = Field(0.0, ge=0, le=1)        # fraction of window with >30min gaps
    speed_anomaly: float = Field(0.0, ge=0, le=1)    # deviation from type-expected speed
    loiter_score: float = Field(0.0, ge=0, le=1)     # time <3kt within 5nm of a point
    night_proximity: float = Field(0.0, ge=0, le=1)  # near origin field 00:00-05:00 local
    type_weight: float = Field(1.0, gt=0)            # tanker/cargo vs passenger
    combined: float = Field(1.0, gt=0)               # the pi_k actually multiplied in


class VesselScore(_Base):
    """One candidate's full scoring breakdown. Every field is shown in the UI."""
    mmsi: str
    vessel_name: str | None = None
    vessel_type: VesselType = VesselType.UNKNOWN

    path_integral: float = Field(..., ge=0)          # L_k = sum Phi(x_k(t),y_k(t),t) dt
    emission_prior: EmissionPrior
    likelihood: float = Field(..., ge=0)             # pi_k * L_k
    posterior: float = Field(..., ge=0, le=1)
    rank: int = Field(..., ge=1)

    # Explainability — the officer needs a reason, not a number.
    closest_approach_km: float = Field(..., ge=0)
    time_at_closest_hours: float                     # relative to observation, negative = before
    phi_mass_explained: float = Field(..., ge=0, le=1)


class LatentSourceScore(_Base):
    """
    M9. The dark-vessel hypothesis L0, competing in the SAME normalisation.

    residual_mass MUST be computed as Phi mass outside the swept corridors of
    all observed tracks. It is NOT a constant. A constant here makes the whole
    latent-source claim vacuous.
    """
    residual_mass: float = Field(..., ge=0, le=1)
    corridor_width_km: float = Field(..., gt=0)      # corridor half-width used
    likelihood: float = Field(..., ge=0)
    posterior: float = Field(..., ge=0, le=1)

    inferred_track: list[GeoPoint] = Field(default_factory=list)
    inferred_release_point: GeoPoint | None = None
    inferred_release_time: datetime | None = None
    dark_detection_ids: list[str] = Field(default_factory=list)   # CHHAYA cross-ref


class AttributionResult(_Base):
    """NYAYA output. The product, if the frontend disappeared."""
    case_id: str
    slick_id: str
    phi_id: str

    verdict: VerdictType
    vessel_scores: list[VesselScore]                 # sorted by posterior desc
    latent_source: LatentSourceScore

    top1_mmsi: str | None = None
    top1_posterior: float = Field(0.0, ge=0, le=1)
    posterior_entropy: float = Field(..., ge=0)      # high entropy -> INCONCLUSIVE

    calibrated: bool = False
    calibration_model_version: str | None = None
    ece: float | None = Field(None, ge=0, le=1)   # from the eval harness, not per-case

    n_candidates_screened: int = Field(..., ge=0)
    n_candidates_scored: int = Field(..., ge=0)
    computed_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _sorted_and_normalised(self) -> AttributionResult:
        ps = [v.posterior for v in self.vessel_scores]
        if ps != sorted(ps, reverse=True):
            raise ValueError("vessel_scores must be sorted by posterior descending")
        total = sum(ps) + self.latent_source.posterior
        if self.vessel_scores and abs(total - 1.0) > 1e-3:
            raise ValueError(f"posterior must sum to 1 with latent source, got {total}")
        return self


# ───────────────────────── CHHAYA (M9b) ─────────────────────────

class DarkVesselDetection(_Base):
    detection_id: str
    scene_id: str
    position: GeoPoint
    length_m: float | None = Field(None, gt=0)
    confidence: float = Field(..., ge=0, le=1)
    matched_mmsi: str | None = None
    is_dark: bool = True                             # no AIS within match radius
    distance_to_slick_km: float | None = Field(None, ge=0)


# ───────────────────────── PRAVAAH (M11) ─────────────────────────

class LandfallPrediction(_Base):
    location_name: str                               # "Marina Beach"
    position: GeoPoint
    eta: datetime
    hours_until: float = Field(..., ge=0)
    probability: float = Field(..., ge=0, le=1)
    coastline_segment_km: float = Field(..., ge=0)


class ForwardForecast(_Base):
    forecast_id: str
    slick_id: str
    horizon_hours: float = Field(..., gt=0)
    landfalls: list[LandfallPrediction] = Field(default_factory=list)
    affected_fishing_zones: list[str] = Field(default_factory=list)
    trajectory_path: str                             # .npz of forward particle positions
    computed_at: datetime = Field(default_factory=_utcnow)


# ───────────────────────── ABHIYAN (07) ─────────────────────────

class SearchBox(_Base):
    bbox: BBox
    center: GeoPoint
    area_km2: float = Field(..., gt=0)
    phi_mass_contained: float = Field(..., ge=0, le=1)


class AssetTasking(_Base):
    asset_type: AssetType
    base_name: str
    search_box: SearchBox
    pattern: str                                     # "expanding_square" | "parallel_track"
    launch_time: datetime
    flight_hours: float = Field(..., gt=0)
    probability_of_detection: float = Field(..., ge=0, le=1)
    rationale: str


# ───────────────────────── PRAMAN (M13) ─────────────────────────

class EvidenceManifest(_Base):
    """Deterministic, checksummed. Answers 'could this stand up in court?'"""
    case_id: str
    scene_ids: list[str]
    model_versions: dict[str, str]                   # {"netra": "...", "chhaya": "..."}
    forcing_versions: dict[str, str]
    parameters: dict[str, Any]
    phi_checksum: str                                # sha256 of the .npz
    posterior_snapshot: dict[str, float]
    chain_of_custody: list[str] = Field(default_factory=list)
    manifest_checksum: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


# ───────────────────────── Top level ─────────────────────────

class Case(_Base):
    """One incident, end to end. Persisted in PostGIS; rendered by the console."""
    case_id: str
    status: CaseStatus = CaseStatus.DETECTED

    detection: SlickDetection
    phi_meta: PhiFieldMeta | None = None
    attribution: AttributionResult | None = None
    forecast: ForwardForecast | None = None
    tasking: AssetTasking | None = None
    dark_detections: list[DarkVesselDetection] = Field(default_factory=list)
    evidence: EvidenceManifest | None = None

    officer_decision: OfficerDecision = OfficerDecision.PENDING
    officer_note: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
