"""
VARUNA GRID — Validity Gate module.
"""
from varuna_contracts.decision import (
    AttributionResultV2, ValidityGateResult, GateCheck, GateReason, DecisionState
)
from varuna_contracts.phi import PhiField
from varuna_contracts.evidence import (
    EvidenceMode, TrustState, ValidityState, Provenance, EvidenceEnvelope
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
        reason_code=None if trust_ok else GateReason.DATA_QUARANTINED,
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
        reason_code=None if conv_ok else GateReason.PHI_NOT_CONVERGED,
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
        reason_code=None if ent_ok else GateReason.PHI_UNINFORMATIVE,
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
        reason_code=None if ec_ok else GateReason.EVIDENCE_INSUFFICIENT,
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
        reason_code=None if loss_ok else GateReason.EVIDENCE_INSUFFICIENT,
    ))
    if not loss_ok:
        caveats.append(f"{loss_frac:.0%} of particles lost to boundaries")

    # Check 6/7: Age and forcing sensitivity. Only run when a real
    # SensitivityBlock exists — see the new phi_diagnostics_availability
    # check below for what happens when it does not (Tranche 1 default,
    # since the sensitivity sweep is a P1 follow-up: see phi_builder.py).
    if phi.sensitivity is not None:
        age_ok = phi.sensitivity.age_sensitivity < 0.7
        checks.append(GateCheck(
            name="age_sensitivity",
            passed=age_ok,
            observed=phi.sensitivity.age_sensitivity,
            threshold=0.7,
            reason_code=None if age_ok else GateReason.EVIDENCE_INSUFFICIENT,
        ))
        if not age_ok:
            caveats.append("Origin driven by age assumption, not data")

        force_ok = phi.sensitivity.forcing_sensitivity < 0.7
        checks.append(GateCheck(
            name="forcing_sensitivity",
            passed=force_ok,
            observed=phi.sensitivity.forcing_sensitivity,
            threshold=0.7,
            reason_code=None if force_ok else GateReason.FORCING_INSUFFICIENT,
        ))
        if not force_ok:
            caveats.append("Result sensitive to forcing choice")

        # Check 7b: Diffusivity sensitivity (ADR-0008). diffusivity_sensitivity
        # is a required, non-Optional SensitivityBlock field (Field(..., ge=0),
        # not float|None like weathering_sensitivity) computed by the exact
        # same procedure as forcing_sensitivity -- ADR-0007 perturbs
        # PratiConfig.diffusivity_range at its existing low/high bounds "the
        # same treatment as forcing" and normalizes on the identical
        # centroid_shift_km / effective_radius_km scale. It is therefore not
        # diagnostic-only: phi.sensitivity.dominant_assumption already treats
        # it as a first-class candidate for "what is driving this origin
        # field", and a validity gate that reads age/forcing but silently
        # ignores diffusivity would miss exactly the case where diffusivity
        # is the dominant, unreported driver. Reusing the 0.7 threshold is
        # not inventing one: it is the same scale, same derivation, same
        # per-axis low/high sweep as forcing_sensitivity, which already uses
        # 0.7. reason_code reuses EVIDENCE_INSUFFICIENT (not
        # FORCING_INSUFFICIENT) because diffusivity is a transport parameter,
        # not a forcing input -- mislabeling it as a forcing problem would
        # send an operator to audit the wrong thing.
        diff_ok = phi.sensitivity.diffusivity_sensitivity < 0.7
        checks.append(GateCheck(
            name="diffusivity_sensitivity",
            passed=diff_ok,
            observed=phi.sensitivity.diffusivity_sensitivity,
            threshold=0.7,
            reason_code=None if diff_ok else GateReason.EVIDENCE_INSUFFICIENT,
        ))
        if not diff_ok:
            caveats.append("Origin driven by diffusivity assumption, not data")
    else:
        # Do NOT fabricate a passing (or failing) sensitivity number just to
        # keep the gate's shape unchanged. Missing diagnostics that the gate
        # policy requires are a BLOCKING condition — the system fails
        # closed rather than trusting a manufactured 0.1.
        checks.append(GateCheck(
            name="phi_diagnostics_availability",
            passed=False,
            detail="SensitivityBlock not computed — sensitivity sweep not yet "
                   "implemented (see phi_builder.py TODO(P1))",
            reason_code=GateReason.PHI_DIAGNOSTICS_UNAVAILABLE,
        ))
        blocking.append(
            "Sensitivity diagnostics unavailable — cannot certify the origin "
            "field is not an artefact of the age/forcing assumptions"
        )

    # Check 8: Posterior entropy
    post_ent_ok = attribution.posterior_entropy < 0.9
    checks.append(GateCheck(
        name="posterior_entropy",
        passed=post_ent_ok,
        observed=attribution.posterior_entropy,
        threshold=0.9,
        reason_code=None if post_ent_ok else GateReason.ATTRIBUTION_UNCERTAIN,
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
        reason_code=None if dist_ok else GateReason.ATTRIBUTION_NOT_DISTINGUISHABLE,
    ))
    if not dist_ok:
        caveats.append("Cannot separate top candidates")

    # Check 10: Evidence mode. SIMULATED evidence must be visible to the
    # officer and must never silently present as REAL — but it is not, on
    # its own, a reason to block a synthetic integration run (the synthetic
    # E2E test in Tranche 1 must still execute end to end). UNAVAILABLE
    # evidence, by contrast, blocks: there is nothing there to act on.
    evidence_mode = attribution.envelope.mode
    if evidence_mode is EvidenceMode.UNAVAILABLE:
        checks.append(GateCheck(
            name="evidence_mode",
            passed=False,
            detail=f"mode={evidence_mode.value}",
            reason_code=GateReason.EVIDENCE_INSUFFICIENT,
        ))
        blocking.append("Evidence is unavailable — nothing to attribute")
    elif evidence_mode is EvidenceMode.SIMULATED:
        checks.append(GateCheck(
            name="evidence_mode",
            passed=True,
            detail=f"mode={evidence_mode.value}",
            reason_code=GateReason.EVIDENCE_SIMULATED,
        ))
        caveats.append("Evidence is SIMULATED — not a real-world observation")
    else:
        checks.append(GateCheck(name="evidence_mode", passed=True, detail="mode=real"))

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
