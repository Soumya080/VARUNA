"""
VARUNA GRID — Configuration for PRATIVARTAN.
"""
from typing import Tuple, Optional
from pydantic import BaseModel, Field

class PratiConfig(BaseModel):
    n_particles: int = Field(default=500, description="Particles per ensemble member")
    n_ensemble: int = Field(default=20, description="Ensemble members M")
    backward_duration_hours: float = Field(description="Computed from age prior, NOT true age")
    dt_seconds: float = Field(default=900.0, description="15-minute timestep")
    grid_resolution_deg: float = Field(default=0.02, description="~2.2 km at equator")
    time_resolution_hours: float = Field(default=1.0)
    wind_drift_range: Tuple[float, float] = Field(default=(0.02, 0.04))
    diffusivity_range: Tuple[float, float] = Field(default=(5.0, 50.0))
    current_noise_range: Tuple[float, float] = Field(default=(0.80, 1.20))
    current_angle_noise_max_deg: float = Field(default=15.0)
    convergence_threshold: float = Field(default=0.15, description="KL divergence threshold")
    min_particles_surviving: float = Field(default=0.80, description="Fraction that must not beach/exit")
    seed: Optional[int] = Field(default=None)
