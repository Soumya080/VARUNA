"""
ADR-0007 (ratified) — build_sensitivity_block() / effective_radius_km().

These exercise the NORMALIZATION only, via directly-constructed PhiField/
SensitivitySweepResult fixtures rather than real ensemble runs — fast and
deterministic, and safe to run at any GPU load since nothing here touches
the ensemble at all. The ensemble-execution side (that the sweep genuinely
re-runs and measures real fields) is covered separately by
tests/unit/test_phi_sensitivity_sweep.py's IMPLEMENTATION SMOKE tests.

Per Phase 8: low / medium / high / boundary / missing / invalid /
monotonicity / determinism.
"""
from datetime import datetime, timezone

import pytest

from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, Provenance
from varuna_contracts.phi import (
    ConvergenceFlag, PhiDiagnostics, PhiField, SensitivityBlock, TimeDistribution,
)
from varuna_contracts.schemas import BBox
from varuna_prativartan.sensitivity import (
    PerturbationRunResult, SensitivitySweepResult,
    build_sensitivity_block, effective_radius_km,
)

pytestmark = pytest.mark.unit


def _phi(effective_support_km2: float, phi_id: str = "phi-1") -> PhiField:
    return PhiField(
        phi_id=phi_id, slick_id="slick-1", case_id="case-1",
        data_path="/tmp/x.npz",
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        grid_shape=(1, 2, 2),
        time_distribution=TimeDistribution(
            time_edges_unix=[0.0, 3600.0], mass=[1.0],
            mode_unix=1800.0, p05_unix=0.0, p95_unix=3600.0,
        ),
        diagnostics=PhiDiagnostics(
            entropy=0.3, concentration=0.5,
            effective_support_km2=effective_support_km2,
            convergence=0.05, convergence_flag=ConvergenceFlag.CONVERGED,
            n_modes=1, particles_seeded=100, ensemble_members_completed=5,
            ensemble_members_requested=5, runtime_seconds=1.0,
        ),
        sensitivity=None,
        n_particles=100, n_ensemble=5, backward_duration_hours=24.0, dt_seconds=900.0,
        forcing_current_source="test", forcing_wind_source="test",
        envelope=EvidenceEnvelope(
            artifact_id=f"env-{phi_id}", produced_by="test",
            provenance=Provenance(source_id="test"), mode=EvidenceMode.SIMULATED,
        ),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _run(label: str, effective_support_km2: float = 100.0) -> PerturbationRunResult:
    return PerturbationRunResult(
        label=label, phi=_phi(effective_support_km2, phi_id=label),
        centroid_lon=0.0, centroid_lat=0.0,
    )


def _sweep(
    *, age_shift_km: float, forcing_shift_km: float, diffusivity_shift_km: float,
    baseline_support_km2: float = 100.0,
) -> SensitivitySweepResult:
    baseline = _run("baseline", baseline_support_km2)
    return SensitivitySweepResult(
        baseline=baseline, age_minus=_run("age_minus"), age_plus=_run("age_plus"),
        forcing_minus=_run("forcing_minus"), forcing_plus=_run("forcing_plus"),
        diffusivity_minus=_run("diffusivity_minus"), diffusivity_plus=_run("diffusivity_plus"),
        age_centroid_shift_km=age_shift_km,
        forcing_centroid_shift_km=forcing_shift_km,
        diffusivity_centroid_shift_km=diffusivity_shift_km,
    )


# ───────────────────────── effective_radius_km ─────────────────────────

def test_effective_radius_is_circular_equivalent_of_area():
    # A = pi * r^2  =>  r = sqrt(A / pi). Pick A = pi so r = 1.0 exactly.
    import math
    phi = _phi(effective_support_km2=math.pi)
    assert effective_radius_km(phi) == pytest.approx(1.0, abs=1e-9)


def test_effective_radius_zero_when_area_zero():
    phi = _phi(effective_support_km2=0.0)
    assert effective_radius_km(phi) == 0.0


# ───────────────────────── low / medium / high sensitivity ─────────────────────────

def test_low_sensitivity_when_shift_much_smaller_than_radius():
    sweep = _sweep(age_shift_km=1.0, forcing_shift_km=1.0, diffusivity_shift_km=1.0,
                    baseline_support_km2=100_000.0)  # huge radius
    block = build_sensitivity_block(sweep)
    assert block.age_sensitivity < 0.1
    assert block.forcing_sensitivity < 0.1
    assert block.diffusivity_sensitivity < 0.1


def test_medium_sensitivity_around_half_radius():
    import math
    radius = 10.0
    area = math.pi * radius ** 2
    sweep = _sweep(age_shift_km=5.0, forcing_shift_km=5.0, diffusivity_shift_km=5.0,
                    baseline_support_km2=area)
    block = build_sensitivity_block(sweep)
    assert block.age_sensitivity == pytest.approx(0.5, rel=1e-6)
    assert block.forcing_sensitivity == pytest.approx(0.5, rel=1e-6)
    assert block.diffusivity_sensitivity == pytest.approx(0.5, rel=1e-6)


def test_high_sensitivity_exceeds_own_radius():
    import math
    radius = 5.0
    area = math.pi * radius ** 2
    sweep = _sweep(age_shift_km=50.0, forcing_shift_km=50.0, diffusivity_shift_km=50.0,
                    baseline_support_km2=area)
    block = build_sensitivity_block(sweep)
    # Shift is 10x the radius -> sensitivity == 10.0, not clipped to 1.0.
    assert block.age_sensitivity == pytest.approx(10.0, rel=1e-6)
    assert block.forcing_sensitivity == pytest.approx(10.0, rel=1e-6)


# ───────────────────────── boundary: exactly the field's own radius ─────────────────────────

def test_boundary_shift_equal_to_radius_scores_exactly_one():
    import math
    radius = 7.0
    area = math.pi * radius ** 2
    sweep = _sweep(age_shift_km=radius, forcing_shift_km=radius, diffusivity_shift_km=radius,
                    baseline_support_km2=area)
    block = build_sensitivity_block(sweep)
    assert block.age_sensitivity == pytest.approx(1.0, rel=1e-6)
    assert block.forcing_sensitivity == pytest.approx(1.0, rel=1e-6)
    assert block.diffusivity_sensitivity == pytest.approx(1.0, rel=1e-6)


def test_boundary_zero_shift_scores_exactly_zero():
    sweep = _sweep(age_shift_km=0.0, forcing_shift_km=0.0, diffusivity_shift_km=0.0)
    block = build_sensitivity_block(sweep)
    assert block.age_sensitivity == 0.0
    assert block.forcing_sensitivity == 0.0
    assert block.diffusivity_sensitivity == 0.0


# ───────────────────────── missing / invalid data ─────────────────────────

def test_weathering_sensitivity_is_none_never_fabricated():
    sweep = _sweep(age_shift_km=1.0, forcing_shift_km=1.0, diffusivity_shift_km=1.0)
    block = build_sensitivity_block(sweep)
    assert block.weathering_sensitivity is None


def test_degenerate_zero_area_baseline_raises_rather_than_fabricating():
    sweep = _sweep(age_shift_km=1.0, forcing_shift_km=1.0, diffusivity_shift_km=1.0,
                    baseline_support_km2=0.0)
    with pytest.raises(ValueError, match="degenerate"):
        build_sensitivity_block(sweep)


def test_sensitivity_block_still_requires_ge_zero():
    with pytest.raises(Exception):
        SensitivityBlock(age_sensitivity=-1.0, forcing_sensitivity=0.0,
                          diffusivity_sensitivity=0.0, weathering_sensitivity=None)


def test_sensitivity_block_weathering_none_is_valid():
    block = SensitivityBlock(age_sensitivity=0.1, forcing_sensitivity=0.1,
                              diffusivity_sensitivity=0.1, weathering_sensitivity=None)
    assert block.weathering_sensitivity is None
    assert block.dominant_assumption in ("age", "forcing", "diffusivity")


# ───────────────────────── monotonicity ─────────────────────────

@pytest.mark.parametrize("shift_km", [0.0, 1.0, 5.0, 10.0, 20.0, 50.0])
def test_sensitivity_is_monotonically_increasing_in_shift(shift_km):
    import math
    radius = 10.0
    area = math.pi * radius ** 2
    sweep = _sweep(age_shift_km=shift_km, forcing_shift_km=0.0, diffusivity_shift_km=0.0,
                    baseline_support_km2=area)
    block = build_sensitivity_block(sweep)
    assert block.age_sensitivity == pytest.approx(shift_km / radius, rel=1e-6)


def test_monotonicity_across_increasing_shifts():
    import math
    radius = 10.0
    area = math.pi * radius ** 2
    shifts = [0.0, 2.0, 4.0, 8.0, 16.0]
    scores = [
        build_sensitivity_block(
            _sweep(age_shift_km=s, forcing_shift_km=0.0, diffusivity_shift_km=0.0,
                   baseline_support_km2=area)
        ).age_sensitivity
        for s in shifts
    ]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)  # strictly increasing, not flat


def test_larger_radius_yields_lower_sensitivity_for_same_shift():
    """A field that is already spread out (large effective radius) is less
    sensitive to the same absolute displacement than a tightly concentrated
    one -- this is the whole point of normalizing by the field's own size."""
    import math
    small_radius_sweep = _sweep(age_shift_km=5.0, forcing_shift_km=0.0, diffusivity_shift_km=0.0,
                                 baseline_support_km2=math.pi * 5.0 ** 2)
    large_radius_sweep = _sweep(age_shift_km=5.0, forcing_shift_km=0.0, diffusivity_shift_km=0.0,
                                 baseline_support_km2=math.pi * 50.0 ** 2)
    small = build_sensitivity_block(small_radius_sweep).age_sensitivity
    large = build_sensitivity_block(large_radius_sweep).age_sensitivity
    assert large < small


# ───────────────────────── determinism ─────────────────────────

def test_build_sensitivity_block_is_deterministic():
    sweep = _sweep(age_shift_km=3.0, forcing_shift_km=4.0, diffusivity_shift_km=5.0,
                    baseline_support_km2=200.0)
    block_a = build_sensitivity_block(sweep)
    block_b = build_sensitivity_block(sweep)
    assert block_a.age_sensitivity == block_b.age_sensitivity
    assert block_a.forcing_sensitivity == block_b.forcing_sensitivity
    assert block_a.diffusivity_sensitivity == block_b.diffusivity_sensitivity


def test_effective_radius_is_deterministic():
    phi = _phi(effective_support_km2=42.0)
    assert effective_radius_km(phi) == effective_radius_km(phi)
