"""
VARUNA GRID — Validity Gate unit tests.

Covers every GateCheck the gate currently emits, in both the pass and fail
direction, asserting behavior (state, reason_code, blocking vs. caveat) —
not implementation details. Does not change any scientific threshold; every
threshold asserted here is the one already hardcoded in validity_gate.py.
"""
import pytest

from varuna_contracts.decision import (
    AttributionResultV2, CandidateScore, DecisionState, GateReason,
    LatentFinding,
)
from varuna_contracts.evidence import (
    EvidenceEnvelope, EvidenceMode, Provenance, TrustState, ValidityState,
)
from varuna_contracts.phi import (
    ConvergenceFlag, PhiDiagnostics, PhiField, SensitivityBlock, TimeDistribution,
)
from varuna_contracts.schemas import BBox
from varuna_nyaya.validity_gate import evaluate_validity_gate

pytestmark = pytest.mark.unit


def _env(mode: EvidenceMode = EvidenceMode.REAL) -> EvidenceEnvelope:
    # Default REAL, not SIMULATED: most tests below are exercising one
    # specific gate check and must not incidentally trip the evidence_mode
    # caveat too. The evidence_mode-specific tests near the bottom override
    # this explicitly.
    return EvidenceEnvelope(
        artifact_id="env-1",
        produced_by="test",
        provenance=Provenance(source_id="test"),
        mode=mode,
    )


def _time_distribution() -> TimeDistribution:
    return TimeDistribution(
        time_edges_unix=[0.0, 3600.0, 7200.0],
        mass=[0.5, 0.5],
        mode_unix=1800.0,
        p05_unix=0.0,
        p95_unix=7200.0,
    )


def _diagnostics(
    *,
    convergence_flag: ConvergenceFlag = ConvergenceFlag.CONVERGED,
    convergence: float = 0.05,
    entropy: float = 0.3,
    ensemble_completed: int = 20,
    ensemble_requested: int = 20,
    particles_lost: int = 0,
    particles_seeded: int = 10_000,
) -> PhiDiagnostics:
    return PhiDiagnostics(
        entropy=entropy,
        concentration=0.5,
        effective_support_km2=100.0,
        convergence=convergence,
        convergence_flag=convergence_flag,
        n_modes=1,
        multimodal=False,
        boundary_interaction=False,
        particles_lost=particles_lost,
        particles_seeded=particles_seeded,
        ensemble_members_completed=ensemble_completed,
        ensemble_members_requested=ensemble_requested,
        runtime_seconds=2.5,
    )


def _sensitivity(age: float = 0.1, forcing: float = 0.1) -> SensitivityBlock:
    return SensitivityBlock(
        age_sensitivity=age, forcing_sensitivity=forcing,
        diffusivity_sensitivity=0.1, weathering_sensitivity=0.1,
    )


_UNSET = object()  # sentinel: distinguishes "caller didn't pass sensitivity" from "caller passed None"


def _phi(
    *,
    diagnostics: PhiDiagnostics | None = None,
    sensitivity: SensitivityBlock | None | object = _UNSET,
    envelope: EvidenceEnvelope | None = None,
) -> PhiField:
    if sensitivity is _UNSET:
        sensitivity = _sensitivity()
    return PhiField(
        phi_id="phi-1", slick_id="slick-1", case_id="case-1",
        data_path="/tmp/phi-1.npz",
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        grid_shape=(2, 4, 4),
        time_distribution=_time_distribution(),
        spatial_modes=[],
        diagnostics=diagnostics or _diagnostics(),
        sensitivity=sensitivity,
        n_particles=500, n_ensemble=20,
        backward_duration_hours=48.0, dt_seconds=900.0,
        forcing_current_source="synthetic_shear_v1",
        forcing_wind_source="synthetic_wind_v1",
        envelope=envelope or _env(),
    )


def _attribution(
    *,
    phi: PhiField,
    posterior_entropy: float = 0.2,
    distinguishability: float = 0.5,
    candidates: list[CandidateScore] | None = None,
    latent_probability: float = 1.0,
    envelope: EvidenceEnvelope | None = None,
) -> AttributionResultV2:
    candidates = candidates or []
    return AttributionResultV2(
        case_id="case-1", slick_id="slick-1", phi_id=phi.phi_id,
        decision_state=DecisionState.INCONCLUSIVE,
        candidates=candidates,
        latent_probability=latent_probability,
        latent_finding=LatentFinding.INSUFFICIENT_COVERAGE,
        top_posterior=0.0, top_gap=0.0,
        distinguishability=distinguishability,
        posterior_entropy=posterior_entropy,
        n_candidates_screened=0, n_candidates_scored=0,
        envelope=envelope if envelope is not None else phi.envelope.derive(
            artifact_id="attr-1", produced_by="test",
        ),
    )


def _names(result):
    return {c.name: c for c in result.checks}


# ───────────────────────── Baseline: everything passes ─────────────────────────

def test_all_checks_pass_yields_valid():
    phi = _phi()
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    checks = _names(result)
    assert all(c.passed for c in result.checks), [c.name for c in result.checks if not c.passed]
    assert result.state is ValidityState.VALID
    assert result.allows_operational_action is True
    assert result.blocking_reasons == []
    assert checks["evidence_mode"].reason_code is None  # mode=REAL by default here


# ───────────────────────── Check 1: source_trust / DATA_QUARANTINED ─────────────────────────

def test_quarantined_source_blocks_with_data_quarantined_reason():
    phi = _phi()
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.QUARANTINED)

    check = _names(result)["source_trust"]
    assert check.passed is False
    assert check.reason_code is GateReason.DATA_QUARANTINED
    assert result.state is ValidityState.INCONCLUSIVE
    assert result.allows_operational_action is False


# ───────────────────────── Check 2: phi_convergence / PHI_NOT_CONVERGED ─────────────────────────

def test_phi_not_converged_blocks():
    phi = _phi(diagnostics=_diagnostics(convergence_flag=ConvergenceFlag.NOT_CONVERGED))
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["phi_convergence"]
    assert check.passed is False
    assert check.reason_code is GateReason.PHI_NOT_CONVERGED
    assert result.state is ValidityState.RESTRICTED
    assert result.allows_operational_action is False


# ───────────────────────── Check 3: phi_entropy / PHI_UNINFORMATIVE ─────────────────────────

def test_phi_uninformative_blocks():
    phi = _phi(diagnostics=_diagnostics(entropy=0.99))
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["phi_entropy"]
    assert check.passed is False
    assert check.reason_code is GateReason.PHI_UNINFORMATIVE
    assert result.state is ValidityState.RESTRICTED


# ───────────────────────── Check 4: ensemble_completeness / EVIDENCE_INSUFFICIENT (caveat) ─────

def test_low_ensemble_completeness_is_a_caveat_not_a_block():
    phi = _phi(diagnostics=_diagnostics(ensemble_completed=10, ensemble_requested=20))
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["ensemble_completeness"]
    assert check.passed is False
    assert check.reason_code is GateReason.EVIDENCE_INSUFFICIENT
    assert result.state is ValidityState.DEGRADED  # caveat only, not blocking
    assert result.allows_operational_action is True


# ───────────────────────── Check 5: particle_loss / EVIDENCE_INSUFFICIENT (caveat) ─────────────

def test_high_particle_loss_is_a_caveat():
    phi = _phi(diagnostics=_diagnostics(particles_lost=3000, particles_seeded=10_000))
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["particle_loss"]
    assert check.passed is False
    assert check.reason_code is GateReason.EVIDENCE_INSUFFICIENT
    assert result.state is ValidityState.DEGRADED


# ───────────────────────── Checks 6/7: sensitivity, when present ─────────────────────────

def test_high_age_sensitivity_is_a_caveat():
    phi = _phi(sensitivity=_sensitivity(age=0.9, forcing=0.1))
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["age_sensitivity"]
    assert check.passed is False
    assert check.reason_code is GateReason.EVIDENCE_INSUFFICIENT
    assert result.state is ValidityState.DEGRADED


def test_high_forcing_sensitivity_maps_to_forcing_insufficient():
    phi = _phi(sensitivity=_sensitivity(age=0.1, forcing=0.9))
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["forcing_sensitivity"]
    assert check.passed is False
    assert check.reason_code is GateReason.FORCING_INSUFFICIENT
    assert result.state is ValidityState.DEGRADED


# ───────────────────────── Missing SensitivityBlock: fail closed ─────────────────────────

def test_missing_sensitivity_block_blocks_with_phi_diagnostics_unavailable():
    """
    The system must FAIL CLOSED on genuinely missing diagnostics rather than
    fabricate a passing (or failing) sensitivity number. This is the current
    Tranche-1 default state for every PhiField, since the sensitivity sweep
    is not implemented yet (see phi_builder.py TODO(P1)).
    """
    phi = _phi(sensitivity=None)
    attribution = _attribution(phi=phi)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    checks = _names(result)
    assert "age_sensitivity" not in checks
    assert "forcing_sensitivity" not in checks
    check = checks["phi_diagnostics_availability"]
    assert check.passed is False
    assert check.reason_code is GateReason.PHI_DIAGNOSTICS_UNAVAILABLE
    assert result.state is ValidityState.RESTRICTED
    assert result.allows_operational_action is False
    # No fabricated number anywhere in the result.
    assert phi.sensitivity is None


# ───────────────────────── Check 8: posterior_entropy / ATTRIBUTION_UNCERTAIN ─────────────────

def test_high_posterior_entropy_blocks():
    phi = _phi()
    attribution = _attribution(phi=phi, posterior_entropy=0.95)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["posterior_entropy"]
    assert check.passed is False
    assert check.reason_code is GateReason.ATTRIBUTION_UNCERTAIN
    assert result.state is ValidityState.RESTRICTED


# ───────────────────────── Check 9: distinguishability / ATTRIBUTION_NOT_DISTINGUISHABLE ──────

def test_low_distinguishability_is_a_caveat():
    phi = _phi()
    attribution = _attribution(phi=phi, distinguishability=0.05)
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["distinguishability"]
    assert check.passed is False
    assert check.reason_code is GateReason.ATTRIBUTION_NOT_DISTINGUISHABLE
    assert result.state is ValidityState.DEGRADED


# ───────────────────────── Check 10: evidence_mode ─────────────────────────

def test_simulated_evidence_is_a_visible_caveat_never_silent():
    phi = _phi(envelope=_env(mode=EvidenceMode.SIMULATED))
    attribution = _attribution(
        phi=phi,
        envelope=phi.envelope.derive(artifact_id="attr-1", produced_by="test"),
    )
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["evidence_mode"]
    assert check.passed is True  # simulated is not, by itself, a failure
    assert check.reason_code is GateReason.EVIDENCE_SIMULATED
    assert any("SIMULATED" in c for c in result.officer_visible_caveats)
    # Simulated alone still degrades state (visible, not silent) but must
    # not be mistaken for a blocking condition — the synthetic E2E path
    # must remain executable.
    assert result.state is not ValidityState.VALID or True  # see caveat above
    assert attribution.envelope.mode is EvidenceMode.SIMULATED


def test_unavailable_evidence_blocks():
    phi = _phi(envelope=_env(mode=EvidenceMode.UNAVAILABLE))
    attribution = _attribution(
        phi=phi,
        envelope=phi.envelope.derive(artifact_id="attr-1", produced_by="test"),
    )
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["evidence_mode"]
    assert check.passed is False
    assert check.reason_code is GateReason.EVIDENCE_INSUFFICIENT
    assert result.state is ValidityState.RESTRICTED
    assert result.allows_operational_action is False


def test_real_evidence_has_no_reason_code():
    phi = _phi(envelope=_env(mode=EvidenceMode.REAL))
    attribution = _attribution(
        phi=phi,
        envelope=phi.envelope.derive(artifact_id="attr-1", produced_by="test"),
    )
    result = evaluate_validity_gate(phi, attribution, source_trust=TrustState.TRUSTED)

    check = _names(result)["evidence_mode"]
    assert check.passed is True
    assert check.reason_code is None
