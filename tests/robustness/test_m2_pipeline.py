"""
VARUNA GRID — M2 Robustness tests.
"""
import pytest
import numpy as np
from experiments.go_nogo_v2.config import GoNoGoConfig
from experiments.go_nogo_v2.truth import generate_case
from experiments.go_nogo_v2.harness import run_case
from varuna_prativartan.config import PratiConfig

def test_m2_pipeline_execution():
    """Verify that the full M2 pipeline runs without raising exceptions."""
    seed = 42
    obs_time_hours = 120.0
    true_age_hours = 24.0
    
    slick_lons, slick_lats, truth_track, decoy_tracks = generate_case(
        seed=seed,
        obs_time_hours=obs_time_hours,
        true_age_hours=true_age_hours,
        is_latent=False
    )
    
    tracks = decoy_tracks + [truth_track]
    
    config = PratiConfig(
        n_particles=100,
        n_ensemble=5,
        backward_duration_hours=true_age_hours,
        seed=seed
    )
    
    res = run_case(
        slick_lons=slick_lons,
        slick_lats=slick_lats,
        obs_time_hours=obs_time_hours,
        tracks=tracks,
        true_mmsi=truth_track.mmsi,
        config=config
    )
    
    assert "pred_mmsi" in res
    assert "is_correct" in res
    assert "gate_state" in res
    
    # We do not assert is_correct here, just that it ran successfully.
