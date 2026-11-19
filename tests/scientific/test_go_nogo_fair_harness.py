from __future__ import annotations

from pathlib import Path

import numpy as np

from experiments.go_nogo.config import QUICK_CONFIG
from experiments.go_nogo.runner import run_trial


def _tiny_config():
    return QUICK_CONFIG.__class__(
        **{
            **QUICK_CONFIG.to_dict(),
            "n_forward_particles": 80,
            "n_backward_particles": 50,
            "n_ensemble_members": 4,
            "grid_time_bins": 8,
            "grid_y_bins": 16,
            "grid_x_bins": 16,
        }
    )


def test_phi_npz_is_normalised(tmp_path: Path):
    result = run_trial(
        slick_age_hours=6.0,
        traffic_density=5,
        forcing_perturbation="moderate",
        ais_uncertainty="clean",
        trial_id=1,
        config=_tiny_config(),
        output_dir=tmp_path,
    )
    data = np.load(result.phi.data_path)
    assert set(data.files) == {"phi", "lon_edges", "lat_edges", "time_edges", "particle_count"}
    assert abs(float(data["phi"].sum()) - 1.0) < 1e-6


def test_seeded_trial_is_reproducible(tmp_path: Path):
    kwargs = dict(
        slick_age_hours=12.0,
        traffic_density=5,
        forcing_perturbation="baseline",
        ais_uncertainty="gaps",
        trial_id=7,
        config=_tiny_config(),
    )
    a = run_trial(**kwargs, output_dir=tmp_path / "a")
    b = run_trial(**kwargs, output_dir=tmp_path / "b")
    assert a.metrics.truth_rank == b.metrics.truth_rank
    assert np.allclose(a.phi.phi, b.phi.phi)
    assert [c.posterior for c in a.attribution.candidates] == [
        c.posterior for c in b.attribution.candidates
    ]


def test_fairness_checks_are_explicit(tmp_path: Path):
    result = run_trial(
        slick_age_hours=24.0,
        traffic_density=20,
        forcing_perturbation="high",
        ais_uncertainty="noisy",
        trial_id=3,
        config=_tiny_config(),
        output_dir=tmp_path,
    )
    assert result.truth_leakage_checks["candidate_tracks_cover_same_envelope"]
    assert result.truth_leakage_checks["true_age_not_passed_as_mean"]
    assert result.metrics.candidate_count == 20
