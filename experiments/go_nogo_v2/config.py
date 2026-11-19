"""
VARUNA GRID — Go/No-Go v2 Experiment Config.
"""
from pydantic import BaseModel, Field

class GoNoGoConfig(BaseModel):
    n_cases: int = Field(default=50, description="Total cases in sweep")
    latent_source_fraction: float = Field(default=0.20, description="Fraction of cases where truth is unknown source")
    obs_time_hours: float = Field(default=120.0, description="Time the slick was observed")
    true_age_hours_range: tuple[float, float] = Field(default=(12.0, 72.0))
    age_prior_std: float = Field(default=24.0, description="Standard deviation for age prior")
    
    # Prativartan parameters
    n_particles: int = Field(default=1000)
    n_ensemble: int = Field(default=30)
