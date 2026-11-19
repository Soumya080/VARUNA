"""Configuration for the fair synthetic go/no-go experiment.

The defaults are deliberately modest so a developer can run a smoke sweep locally. Full
scientific claims require many more trials than these defaults provide.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ExperimentConfig:
    seed: int = 42
    scenario_seed: int = 1000
    forcing_seed: int = 2000
    candidate_seed: int = 3000

    slick_ages_hours: tuple[float, ...] = (2.0, 6.0, 12.0, 24.0, 48.0)
    traffic_densities: tuple[int, ...] = (5, 20, 50, 100)
    forcing_perturbations: tuple[str, ...] = ("baseline", "moderate", "high")
    ais_uncertainties: tuple[str, ...] = ("clean", "gaps", "noisy")
    trials_per_cell: int = 3

    release_lon: float = 72.0
    release_lat: float = 15.0
    observation_time_hours: float | None = None

    n_forward_particles: int = 400
    n_backward_particles: int = 300
    n_ensemble_members: int = 16
    dt_seconds: float = 1800.0
    grid_time_bins: int = 20
    grid_y_bins: int = 48
    grid_x_bins: int = 48

    wind_drift_factor: float = 0.03
    diffusivity_m2s: float = 8.0
    release_radius_km: float = 0.35
    hard_negative_fraction: float = 0.35
    track_corridor_km: float = 4.0

    model_version: str = "go_nogo_fair_v0.1"
    output_root: str = "experiments/results/go_nogo"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


QUICK_CONFIG = ExperimentConfig(
    slick_ages_hours=(6.0, 24.0),
    traffic_densities=(5, 20),
    forcing_perturbations=("moderate",),
    ais_uncertainties=("clean", "gaps"),
    trials_per_cell=2,
    n_forward_particles=250,
    n_backward_particles=160,
    n_ensemble_members=8,
    grid_time_bins=14,
    grid_y_bins=36,
    grid_x_bins=36,
)


def config_from_dict(raw: dict[str, object]) -> ExperimentConfig:
    """Create a config from JSON, preserving tuple-valued fields."""
    tuple_fields = {
        "slick_ages_hours",
        "traffic_densities",
        "forcing_perturbations",
        "ais_uncertainties",
    }
    values = {}
    for field_name in ExperimentConfig.__dataclass_fields__:
        if field_name not in raw:
            continue
        value = raw[field_name]
        values[field_name] = tuple(value) if field_name in tuple_fields else value
    return ExperimentConfig(**values)
