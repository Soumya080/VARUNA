"""
VARUNA GRID — Validity Gate module.
"""
from varuna_contracts.decision import (
    AttributionResultV2, ValidityGateResult, GateCheck, DecisionState
)
from varuna_contracts.phi import PhiField
from varuna_contracts.evidence import (
    TrustState, ValidityState, Provenance, EvidenceEnvelope
)


def evaluate_validity_gate(
    phi: PhiField,
    attribution: AttributionResultV2,
    source_trust: TrustState,
) -> ValidityGateResult:
    checks = []
    blocking = []
    caveats = []

    # Check 1: Source trust
    trust_ok = source_trust != TrustState.QUARANTINED
    checks.append(GateCheck(
        name="source_trust",
        passed=trust_ok,
        detail=f"trust={source_trust.value}",
    ))
    if not trust_ok:
        blocking.append("Input data quarantined — zero influence permitted")

    # Check 2: Φ convergence
    conv_ok = phi.diagnostics.convergence_flag.is_usable
    checks.append(GateCheck(
        name="phi_convergence",
        passed=conv_ok,
        observed=phi.diagnostics.convergence,
        threshold=0.15,
        detail=f"flag={phi.diagnostics.convergence_flag.value}",
    ))
    if not conv_ok:
        blocking.append("Origin field did not converge")

    # Check 3: Φ entropy
    ent_ok = phi.diagnostics.entropy < 0.95
    checks.append(GateCheck(
        name="phi_entropy",
        passed=ent_ok,
        observed=phi.diagnostics.entropy,
        threshold=0.95,
    ))
    if not ent_ok:
        blocking.append("Origin field is near-uniform — no spatial discrimination")

    # Check 4: Ensemble completeness
    ec = phi.diagnostics.ensemble_completeness
    ec_ok = ec >= 0.8
    checks.append(GateCheck(
        name="ensemble_completeness",
        passed=ec_ok,
        observed=ec,
        threshold=0.8,
    ))
    if not ec_ok:
        caveats.append(f"Only {ec:.0%} of ensemble members completed")

    # Check 5: Particle loss
    loss_frac = 0.0
    if phi.diagnostics.particles_seeded > 0:
        loss_frac = phi.diagnostics.particles_lost / phi.diagnostics.particles_seeded
    loss_ok = loss_frac <= 0.2
    checks.append(GateCheck(
        name="particle_loss",
        passed=loss_ok,
        observed=loss_frac,
        threshold=0.2,
    ))
    if not loss_ok:
        caveats.append(f"{loss_frac:.0%} of particles lost to boundaries")

    # Check 6: Age sensitivity
    age_ok = phi.sensitivity.age_sensitivity < 0.7
    checks.append(GateCheck(
        name="age_sensitivity",
        passed=age_ok,
        observed=phi.sensitivity.age_sensitivity,
        threshold=0.7,
    ))
    if not age_ok:
        caveats.append("Origin driven by age assumption, not data")

    # Check 7: Forcing sensitivity
    force_ok = phi.sensitivity.forcing_sensitivity < 0.7
    checks.append(GateCheck(
        name="forcing_sensitivity",
        passed=force_ok,
        observed=phi.sensitivity.forcing_sensitivity,
        threshold=0.7,
    ))
    if not force_ok:
        caveats.append("Result sensitive to forcing choice")

    # Check 8: Posterior entropy
    post_ent_ok = attribution.posterior_entropy < 0.9
    checks.append(GateCheck(
        name="posterior_entropy",
        passed=post_ent_ok,
        observed=attribution.posterior_entropy,
        threshold=0.9,
    ))
    if not post_ent_ok:
        blocking.append("Posterior is near-flat — cannot rank candidates")

    # Check 9: Distinguishability
    dist_ok = attribution.distinguishability >= 0.1
    checks.append(GateCheck(
        name="distinguishability",
        passed=dist_ok,
        observed=attribution.distinguishability,
        threshold=0.1,
    ))
    if not dist_ok:
        caveats.append("Cannot separate top candidates")

    # Determine state
    if blocking:
        if source_trust == TrustState.QUARANTINED:
            state = ValidityState.INCONCLUSIVE
        else:
            state = ValidityState.RESTRICTED
    elif caveats:
        state = ValidityState.DEGRADED
    else:
        state = ValidityState.VALID

    # Derive envelope
    out_env = attribution.envelope.derive(
        artifact_id=f"gate-{attribution.case_id}",
        produced_by="validity_gate",
        validity=state,
    )

    return ValidityGateResult(
        case_id=attribution.case_id,
        state=state,
        checks=checks,
        blocking_reasons=blocking,
        officer_visible_caveats=caveats,
        source_trust=source_trust,
        envelope=out_env,
    )
