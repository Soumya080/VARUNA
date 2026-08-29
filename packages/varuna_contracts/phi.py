"""
VARUNA GRID v2 — Phi is a STRUCTURED OBJECT, not an image.

v1 treated Phi as a heatmap array plus loose metadata. That made it impossible for
NYAYA to know whether the field was trustworthy, so the INCONCLUSIVE decision had
to be reverse-engineered downstream from a number that had already lost its context.

In v2, PRATIVARTAN reports its own uncertainty as first-class diagnostics. NYAYA
reads them; it does not re-derive them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from varuna_contracts.evidence import EvidenceEnvelope
from varuna_contracts.schemas import BBox, GeoPoint

__all__ = [
    "ConvergenceFlag",
    "PhiDiagnostics",
    "PhiField",
    "SensitivityBlock",
    "SpatialMode",
    "TimeDistribution",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ConvergenceFlag(StrEnum):
    CONVERGED = "converged"
    MARGINAL = "marginal"
    NOT_CONVERGED = "not_converged"
    INSUFFICIENT_PARTICLES = "insufficient_particles"

    @property
    def is_usable(self) -> bool:
        return self in (ConvergenceFlag.CONVERGED, ConvergenceFlag.MARGINAL)


class SpatialMode(_Base):
    """One distinct lobe of the origin field. >1 mode means competing hypotheses."""
    centroid: GeoPoint
    mass: float = Field(..., ge=0, le=1)
    area_km2: float = Field(..., ge=0)
    peak_time_unix: float
    separation_km: float | None = Field(None, ge=0)  # distance to nearest other mode


class TimeDistribution(_Base):
    """Marginal posterior over RELEASE TIME. The 'when', separate from the 'where'."""
    time_edges_unix: list[float] = Field(..., min_length=2)
    mass: list[float] = Field(..., min_length=1)
    mode_unix: float
    p05_unix: float
    p95_unix: float

    @model_validator(mode="after")
    def _shapes(self) -> TimeDistribution:
        if len(self.mass) != len(self.time_edges_unix) - 1:
            raise ValueError("mass must have len(time_edges) - 1 entries")
        if self.p05_unix > self.p95_unix:
            raise ValueError("p05 must be <= p95")
        return self


class SensitivityBlock(_Base):
    """
    How much does Phi move when an ASSUMPTION moves? These are the numbers that
    make the honesty claim defensible: if age_sensitivity is high, the origin
    field is an artefact of the age prior, not of the data.

    Each value is a normalised displacement, `0 = insensitive`, `1 = the
    field moves by its own effective radius under a 1-sigma perturbation`
    (see packages/varuna_prativartan/sensitivity.py::build_sensitivity_block
    for the ratified ADR-0007 computation — displacement is not capped at
    1; a shift larger than the field's own radius is a real, reportable
    value above 1, not an error).

    `weathering_sensitivity` is `float | None` (ADR-0007 amendment) because
    no weathering model exists in PRATIVARTAN at all — `PhiField.
    weathering_model` is always `None` in this codebase. There is nothing
    to perturb, so this is honestly `None` rather than a number standing
    in for physics that isn't implemented. The other three axes ARE real
    perturbable parameters (age prior, forcing noise, diffusivity) and
    remain required.
    """
    age_sensitivity: float = Field(..., ge=0)
    forcing_sensitivity: float = Field(..., ge=0)
    diffusivity_sensitivity: float = Field(..., ge=0)
    weathering_sensitivity: float | None = Field(None, ge=0)

    @property
    def dominant_assumption(self) -> str:
        candidates = [
            ("age", self.age_sensitivity), ("forcing", self.forcing_sensitivity),
            ("diffusivity", self.diffusivity_sensitivity),
        ]
        if self.weathering_sensitivity is not None:
            candidates.append(("weathering", self.weathering_sensitivity))
        return max(candidates, key=lambda kv: kv[1])[0]


class PhiDiagnostics(_Base):
    """First-class quality report. NYAYA's Validity Gate reads THIS, not the array."""
    entropy: float = Field(..., ge=0)                    # normalised spatial entropy [0,1]
    concentration: float = Field(..., ge=0, le=1)        # mass in the top 5% of cells
    effective_support_km2: float = Field(..., ge=0)      # area holding 90% of mass
    convergence: float = Field(..., ge=0)                # ensemble-split divergence metric
    convergence_flag: ConvergenceFlag
    n_modes: int = Field(..., ge=0)
    multimodal: bool = False
    boundary_interaction: bool = False                   # mass touching coast/domain edge
    particles_lost: int = Field(0, ge=0)
    particles_seeded: int = Field(..., gt=0)
    ensemble_members_completed: int = Field(..., ge=0)
    ensemble_members_requested: int = Field(..., gt=0)
    runtime_seconds: float = Field(..., ge=0)

    @property
    def ensemble_completeness(self) -> float:
        return self.ensemble_members_completed / self.ensemble_members_requested

    @property
    def is_degraded(self) -> bool:
        return (
            not self.convergence_flag.is_usable
            or self.ensemble_completeness < 0.8
            or self.particles_lost > 0.2 * self.particles_seeded
        )


class PhiField(_Base):
    """
    The complete origin-probability artifact handed from PRATIVARTAN to NYAYA.

    The numeric array lives at `data_path` as .npz with EXACTLY these keys:
        phi            float32 (n_t, n_y, n_x)   sum == 1.0
        lon_edges      float64 (n_x + 1,)
        lat_edges      float64 (n_y + 1,)
        time_edges     float64 (n_t + 1,)        unix seconds UTC
        particle_count int32   (n_t,)

    Everything else about the field lives here, in structured form.
    """
    phi_id: str
    slick_id: str
    case_id: str
    data_path: str
    bbox: BBox
    grid_shape: tuple[int, int, int]                     # (n_t, n_y, n_x)

    time_distribution: TimeDistribution
    spatial_modes: list[SpatialMode] = Field(default_factory=list)
    diagnostics: PhiDiagnostics
    # None means "not computed", not "computed and found to be zero".
    # `phi_builder.build_phi_field()`'s default path always leaves this
    # None (a real sweep costs 7x the ensemble runtime); a real,
    # non-fabricated sweep exists at
    # varuna_prativartan.sensitivity.run_sensitivity_sweep() +
    # build_sensitivity_block() (ADR-0007, ratified) for callers that
    # explicitly request it. The validity gate treats None as
    # PHI_DIAGNOSTICS_UNAVAILABLE (blocking).
    sensitivity: SensitivityBlock | None = None

    n_particles: int = Field(..., gt=0)
    n_ensemble: int = Field(..., gt=0)
    backward_duration_hours: float = Field(..., gt=0)
    dt_seconds: float = Field(..., gt=0)

    forcing_current_source: str
    forcing_wind_source: str
    weathering_model: str | None = None

    envelope: EvidenceEnvelope
    created_at: datetime | None = None

    @property
    def primary_mode(self) -> SpatialMode | None:
        return max(self.spatial_modes, key=lambda m: m.mass) if self.spatial_modes else None
