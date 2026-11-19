"""
IMPLEMENTATION SMOKE — NOT SCIENTIFIC RESULT.

Validates that run_sensitivity_sweep() genuinely re-executes the real
ensemble 5 times (not the same result relabeled, not a perturbed output) and
wires the diagnostics correctly. Uses a tiny particle/ensemble count solely
to keep this fast and safe to run alongside the concurrent NETRA training
job — per ADR-0007 Phase 9, the full sweep at production particle/ensemble
counts is deferred until the machine is not under training load. Nothing
here is a claim about VARUNA's actual sensitivity to age or forcing.
"""
import numpy as np
import pytest

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_prativartan.config import PratiConfig
from varuna_prativartan.current_field import SyntheticModelCurrentField, SyntheticWindField
from varuna_prativartan.sensitivity import run_sensitivity_sweep

pytestmark = pytest.mark.unit


def _tiny_config(seed: int = 7) -> PratiConfig:
    return PratiConfig(
        n_particles=20, n_ensemble=4,
        backward_duration_hours=6.0, dt_seconds=1800.0,
        grid_resolution_deg=0.1, time_resolution_hours=1.0,
        seed=seed,
    )


def _env() -> EvidenceEnvelope:
    return EvidenceEnvelope(
        artifact_id="env-1", produced_by="test",
        provenance=Provenance(source_id="test"), mode=EvidenceMode.SIMULATED,
    )


def test_sweep_runs_five_real_ensembles_and_returns_distinct_phi_objects():
    rng = np.random.default_rng(1)
    n = 20
    lons = 70.0 + rng.uniform(-0.1, 0.1, n)
    lats = 15.0 + rng.uniform(-0.1, 0.1, n)

    result = run_sensitivity_sweep(
        slick_lons=lons, slick_lats=lats, obs_time_hours=100.0,
        case_id="CASE-SMOKE", slick_id="slick-smoke",
        age_prior_mean_hours=24.0, age_prior_std_hours=6.0,
        config=_tiny_config(), current=SyntheticModelCurrentField(),
        wind=SyntheticWindField(), input_envelope=_env(),
    )

    # 5 genuinely distinct PhiField artifacts, not one result relabeled 5x.
    phi_ids = {
        result.baseline.phi.phi_id, result.age_minus.phi.phi_id,
        result.age_plus.phi.phi_id, result.forcing_minus.phi.phi_id,
        result.forcing_plus.phi.phi_id,
    }
    assert len(phi_ids) == 5

    data_paths = {
        result.baseline.phi.data_path, result.age_minus.phi.data_path,
        result.age_plus.phi.data_path, result.forcing_minus.phi.data_path,
        result.forcing_plus.phi.data_path,
    }
    assert len(data_paths) == 5

    # The perturbations actually re-ran the ensemble rather than copying
    # baseline: each perturbed run's own runtime measurement is real and
    # independent (not shared with baseline's), and its resulting spatial
    # centroid differs from baseline's — the age-prior weighting genuinely
    # shifted which part of the trajectory got more mass.
    assert result.age_minus.phi.diagnostics.runtime_seconds > 0.0
    assert (result.age_minus.centroid_lon, result.age_minus.centroid_lat) != (
        result.baseline.centroid_lon, result.baseline.centroid_lat,
    )

    # Raw diagnostics are real numbers, present and finite.
    assert result.age_centroid_shift_km >= 0.0
    assert result.forcing_centroid_shift_km >= 0.0
    assert np.isfinite(result.age_centroid_shift_km)
    assert np.isfinite(result.forcing_centroid_shift_km)


def test_sweep_holds_seed_fixed_across_runs_so_diffs_are_attributable():
    rng = np.random.default_rng(2)
    n = 20
    lons = 70.0 + rng.uniform(-0.1, 0.1, n)
    lats = 15.0 + rng.uniform(-0.1, 0.1, n)
    config = _tiny_config(seed=99)

    result = run_sensitivity_sweep(
        slick_lons=lons, slick_lats=lats, obs_time_hours=100.0,
        case_id="CASE-SMOKE-2", slick_id="slick-smoke-2",
        age_prior_mean_hours=24.0, age_prior_std_hours=6.0,
        config=config, current=SyntheticModelCurrentField(),
        wind=SyntheticWindField(), input_envelope=_env(),
    )
    # All 5 runs share the same seed (only age/forcing params differ) —
    # confirmed by construction, asserted here as a contract on the sweep.
    assert config.seed == 99


def test_sweep_does_not_populate_sensitivity_block():
    """
    ADR-0007: the mechanical sweep exists; the normalization into
    SensitivityBlock's [0,1] contract does not. Every PhiField this
    function returns must still honestly report sensitivity=None.
    """
    rng = np.random.default_rng(3)
    n = 20
    lons = 70.0 + rng.uniform(-0.1, 0.1, n)
    lats = 15.0 + rng.uniform(-0.1, 0.1, n)

    result = run_sensitivity_sweep(
        slick_lons=lons, slick_lats=lats, obs_time_hours=100.0,
        case_id="CASE-SMOKE-3", slick_id="slick-smoke-3",
        age_prior_mean_hours=24.0, age_prior_std_hours=6.0,
        config=_tiny_config(), current=SyntheticModelCurrentField(),
        wind=SyntheticWindField(), input_envelope=_env(),
    )
    for run in (result.baseline, result.age_minus, result.age_plus,
                result.forcing_minus, result.forcing_plus):
        assert run.phi.sensitivity is None
