# ADR-0008 — Diffusivity Sensitivity Gate Policy

**Status:** Accepted · **Date:** 31 Aug 2026

## Context

Track 2 final production integration (Task 3) required auditing whether
`SensitivityBlock.diffusivity_sensitivity` should affect Validity Gate
outcomes. Prior to this ADR, `packages/varuna_nyaya/validity_gate.py`
computed and gated on `age_sensitivity` and `forcing_sensitivity` (Checks
6/7) but never read `diffusivity_sensitivity` at all — the value was
computed by `build_sensitivity_block()` (ADR-0007) and shipped on every
`PhiField.sensitivity`, but the gate silently ignored it.

## Evidence from existing contracts, ADRs, and code

1. **Contract declaration.** `packages/varuna_contracts/phi.py`:
   `diffusivity_sensitivity: float = Field(..., ge=0)` — required, no
   default, no `Optional`. This is the same declaration shape as
   `age_sensitivity` and `forcing_sensitivity`. `weathering_sensitivity` is
   the one axis marked `float | None` because "no weathering model exists
   in PRATIVARTAN at all." The contract's own type distinction already
   separates "real, required, perturbable" (age/forcing/diffusivity) from
   "physically unavailable" (weathering) — diffusivity is on the required
   side.

2. **Docstring.** Same file, immediately above the field declarations: *"The
   other three axes ARE real perturbable parameters (age prior, forcing
   noise, diffusivity) and remain required."* This groups diffusivity with
   age and forcing as a load-bearing axis, not a diagnostic-only extra.

3. **`dominant_assumption` property.** Already treats `diffusivity` as a
   first-class candidate for "which assumption is actually driving this
   origin field" (`packages/varuna_contracts/phi.py`). A gate that reads
   age/forcing but not diffusivity can report an origin field as
   sensitivity-clean while `dominant_assumption == "diffusivity"` — the
   caveat and the underlying diagnostic would disagree.

4. **ADR-0007 computation.** `diffusivity_sensitivity` is computed by
   perturbing `PratiConfig.diffusivity_range` at its existing low/high
   bounds and normalizing via the ratified
   `centroid_shift_km / effective_radius_km` formula — explicitly "the same
   treatment as forcing." It is not a lesser-quality or less-defensible
   number than `forcing_sensitivity`; it is produced by the identical
   procedure on the identical scale.

5. **No existing diffusivity-specific threshold exists anywhere** (contract,
   tests, docs) — confirmed by search. Nothing has ever been decided about
   *where* to cut it. This was the genuinely open question.

## Decision

**A. `diffusivity_sensitivity` affects validity — it is gated, not
diagnostic-only**, for the reasons above: the contract, its docstring, and
`dominant_assumption` already treat it as a peer of age/forcing, and ADR-0007
computes it on exactly the same scale via exactly the same procedure as
`forcing_sensitivity`.

**Threshold: reuse 0.7**, the existing age/forcing threshold, not a new
invented number. This is justified by identity of scale and derivation, not
by convenience: `forcing_sensitivity` and `diffusivity_sensitivity` are both
produced by pinning a `PratiConfig` range to its existing uniform-sampling
bounds and normalizing by the same `effective_radius_km` — they are the same
*kind* of measurement, differing only in which physical parameter is
perturbed. Inventing a distinct threshold for diffusivity with no evidence
to calibrate it against would be less defensible than reusing the one
threshold already ratified for a sibling axis measured the same way.

**Reason code: `GateReason.EVIDENCE_INSUFFICIENT`**, not
`GateReason.FORCING_INSUFFICIENT`. Diffusivity is a transport
(diffusion-coefficient) parameter of PRATIVARTAN's advection model, not a
forcing input (wind/current) — reusing `FORCING_INSUFFICIENT` would send an
operator to audit the wrong subsystem. `EVIDENCE_INSUFFICIENT` matches the
generic code `age_sensitivity` already uses for the same category of
concern ("origin driven by an assumption, not by data"), and no
diffusivity-specific `GateReason` exists — adding one would be a
`varuna_contracts` change requiring its own ADR for a purely cosmetic label,
which is not justified here.

**Severity: caveat (non-blocking), matching `age_sensitivity`'s existing
severity**, not `forcing_sensitivity`'s (which is also non-blocking — no
sensitivity check in the current gate is blocking; `phi_diagnostics_
availability`, the *absence* of a `SensitivityBlock`, is the blocking
condition). A high `diffusivity_sensitivity` is visible to the officer via
`officer_visible_caveats` exactly like age/forcing, and continues to allow
`DEGRADED` (operational, with caveat) rather than `RESTRICTED`.

## Consequences

**Positive**
- Closes a real gap: a diagnostic computed for every case was previously
  invisible to the gate and to the officer.
- No new threshold invented; no new contract field; no new `GateReason`
  member. Implementation is a ~25-line addition to
  `evaluate_validity_gate()`, guarded by the same `phi.sensitivity is not
  None` branch that already gates age/forcing.
- `dominant_assumption == "diffusivity"` cases now surface a caveat, closing
  the disagreement described in point 3 above.

**Negative / residual**
- Reusing 0.7 is a reasoned extension, not an independently-calibrated
  diffusivity-specific threshold. If future evidence shows diffusivity
  perturbations behave differently in practice from forcing perturbations
  (e.g. a different typical centroid-shift magnitude), this threshold should
  be revisited — flagged as a P1 follow-up, not resolved here.
- This changes `ValidityGateResult.checks` shape (one more `GateCheck` when
  `phi.sensitivity is not None`) and can newly add a caveat that was not
  previously present for already-computed sensitivity sweeps. Any caller
  asserting an exact `checks` count or an exact `officer_visible_caveats`
  list needs to account for the new entry — covered by
  `tests/unit/test_validity_gate.py`.

## Not done

- No change to `phi_builder.py`'s default (cheap) path — `PhiField.
  sensitivity` remains `None` unless a caller explicitly invokes
  `reconstruct_origin_with_sensitivity()`. This ADR only changes what the
  gate does *when* a `SensitivityBlock` is present.
- No change to the age/forcing thresholds or their reason codes.
- No new `GateReason` enum member.
