"""
VARUNA GRID — Backward ensemble runner.
"""
import numpy as np
from typing import List, Tuple
from varuna_prativartan.config import PratiConfig
from varuna_prativartan.engine import advect_particles
from varuna_prativartan.current_field import AbstractCurrentField, AbstractWindField

def run_backward_ensemble(
    obs_lons: np.ndarray,
    obs_lats: np.ndarray,
    obs_time_hours: float,
    current: AbstractCurrentField,
    wind: AbstractWindField,
    config: PratiConfig,
) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Run M-member backward ensemble with structurally perturbed forcing.
    """
    rng = np.random.default_rng(config.seed)
    n_obs = len(obs_lons)
    results = []
    
    wdf_lo, wdf_hi = config.wind_drift_range
    diff_lo, diff_hi = config.diffusivity_range
    cnf_lo, cnf_hi = config.current_noise_range
    cad_max = config.current_angle_noise_max_deg
    
    for m in range(config.n_ensemble):
        # Sample parameters
        wdf = rng.uniform(wdf_lo, wdf_hi)
        diff = rng.uniform(diff_lo, diff_hi)
        cnf = rng.uniform(cnf_lo, cnf_hi)
        cad = rng.uniform(-cad_max, cad_max)
        
        # Subsample particles
        if config.n_particles < n_obs:
            indices = rng.choice(n_obs, config.n_particles, replace=False)
        else:
            indices = np.arange(n_obs)
            
        lons = obs_lons[indices]
        lats = obs_lats[indices]
        
        hist_lons, hist_lats, hist_times = advect_particles(
            lons=lons,
            lats=lats,
            current=current,
            wind=wind,
            wind_drift_factor=wdf,
            diffusivity=diff,
            duration_hours=config.backward_duration_hours,
            dt_seconds=config.dt_seconds,
            rng=rng,
            current_noise_factor=cnf,
            current_angle_noise_deg=cad,
            start_time_hours=obs_time_hours,
            backward=True,
        )
        
        results.append((hist_lons, hist_lats, hist_times))
        
    return results
