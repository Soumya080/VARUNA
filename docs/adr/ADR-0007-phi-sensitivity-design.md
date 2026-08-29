# ADR-0007 — Φ Sensitivity Sweep Design

**Status:** Proposed (mechanics implemented, one normalization decision open) · **Date:** 29 Aug 2026

## Context

`SensitivityBlock` has been `None` since ADR-0006 rather than the fabricated `age_sensitivity=
forcing_sensitivity=0.1` literals it previously carried, because no perturbation sweep had ever
been run. This ADR is the design step Track 2 Phase 5 requires before writing that sweep: identify
the baseline parameters and perturbation ranges from the project's *existing* scientific
configuration, and do not invent new ones.

### What already exists and can be reused verbatim

- **Age axis:** `PrativartanService.reconstruct_origin(age_prior_mean_hours, age_prior_std_hours,
  ...)` already receives a real 1-sigma uncertainty for the release-age assumption. This is exactly
  the "1-sigma perturbation" `PhiDiagnostics`/`SensitivityBlock`'s docstring already asks for
  (`packages/varuna_contracts/phi.py`: *"1 = the field moves by its own effective radius under a
  1-sigma perturbation"*). No new age range needs to be invented — perturbing
  `age_prior_mean_hours` by `± age_prior_std_hours` (holding forcing fixed) is the existing
  parameter, reused, not a new assumption.
- **Forcing axis:** `PratiConfig` already defines three numeric ranges the ensemble samples
  per-member — `wind_drift_range=(0.02, 0.04)`, `diffusivity_range=(5.0, 50.0)`,
  `current_noise_range=(0.80, 1.20)` — plus `current_angle_noise_max_deg=15.0`. These already exist
  and are already used for exactly this kind of perturbation (structurally perturbed forcing across
  ensemble members, per `ensemble.py`'s own docstring). Re-running the ensemble at the low bound vs.
  the high bound of `current_noise_range` (the dominant of the three for how far particles travel;
  holding `wind_drift_range`/`diffusivity_range` at their existing per-run sampling) is a reuse of an
  existing range, not a new one.
- **A real distance metric between two Φ fields already exists.** ADR-0006's honest `convergence`
  computation (`phi_builder.py`) is a total-variation divergence between two half-ensemble lat/lon
  histograms on a shared grid. The identical computation applies unchanged to "baseline Φ vs.
  perturbed Φ" — it does not need to be reinvented for this ADR.

A categorical precedent also exists in `experiments/go_nogo/prativartan.py` (a separate, older
go/no-go experiment harness, not the production path) — `forcing_perturbations = ("baseline",
"moderate", "high")` with an `age_sensitivity` computed for real from perturbation-run samples, but
`forcing_sensitivity` there is itself a **hardcoded lookup table**
(`{"baseline": 0.15, "moderate": 0.45, "high": 0.75}`) — the same category of fabrication ADR-0006
removed from `phi_builder.py`. This ADR does not import that lookup table or its categorical
convention into the production path.

### The one genuinely open decision

`SensitivityBlock`'s contract requires a **normalized displacement in `[0, 1]`: 0 = insensitive, 1
= the field moves by its own effective radius under a 1-sigma perturbation.** A total-variation
divergence between baseline and perturbed Φ is a real, computable `[0, 1]` quantity, but it is not
the same thing as "displacement measured in units of the field's own effective radius" — TV
divergence saturates at 1.0 for *any* two distributions with disjoint support, however close
together they sit, while a radius-normalized displacement should scale continuously with how far
the field's mass actually moved relative to how spread out it already is.

No specification anywhere in this repository defines the conversion from a measured field
difference to that specific radius-normalized quantity. This is not a value to guess — it is a
methodological choice that changes what "0.7" (the validity gate's existing, unmodified threshold)
actually means. Guessing it would silently redefine the gate's threshold's meaning without anyone
deciding to.

## Decision

**Split the work at exactly this boundary.**

1. **Implemented now, mechanically, in `packages/varuna_prativartan/sensitivity.py`:** a function
   that re-runs the real ensemble (`run_backward_ensemble` → `build_phi_field`, unmodified) three
   times per axis — perturbed-low, baseline, perturbed-high — using only the existing parameters
   above, and returns the *raw* measured differences: the same total-variation divergence already
   implemented for `convergence`, the centroid shift in km between the baseline and perturbed
   field's lat/lon spatial marginal, the `n_modes`/`convergence_flag`/`ensemble_completeness` deltas
   Phase 6 asks for, and full runtime/provenance for each of the three runs. This is genuinely new
   ensemble execution against real inputs — not perturbing an already-computed output, not added
   noise, not a relabeled reuse of one result (see `PerturbationRunResult` and
   `SensitivitySweepResult` in that module).

2. **Not implemented yet:** the conversion from that raw `SensitivitySweepResult` into the exact
   `age_sensitivity`/`forcing_sensitivity` scalars `SensitivityBlock` requires. Until a normalization
   convention is ratified as a follow-up to this ADR, `PhiField.sensitivity` remains `None` and the
   validity gate continues to report `PHI_DIAGNOSTICS_UNAVAILABLE` (blocking) exactly as ADR-0006
   left it — this ADR does not change gate behavior, and does not populate `SensitivityBlock` with a
   guessed number merely because the mechanical sweep now exists.

A candidate normalization (not yet adopted, listed here so the follow-up decision has a concrete
starting point rather than a blank page): divide the perturbed field's centroid shift by an
effective radius derived from the *baseline* field's own `effective_support_km2`
(`radius_km = sqrt(effective_support_km2 / pi)`), clipped to `[0, 1]`. This treats "moved by its own
radius" literally. It is not adopted by this ADR because no one has confirmed it is the intended
reading of the docstring's "1 = the field moves by its own effective radius" versus an entropy- or
divergence-based alternative.

## Consequences

**Positive**
- The mechanical sweep is real, tested (see `tests/unit/test_phi_sensitivity_sweep.py`), and
  reuses only parameters and metrics that already existed before this ADR — nothing here is a new
  scientific assumption.
- The one open question is now written down precisely enough that ratifying it is a short follow-up
  ADR amendment, not a research project.
- `SensitivityBlock` staying `None` until that ratification keeps the gate honest — a wrong-but-
  confident number would have been worse than the current, correctly blocking `None`.

**Negative**
- `PHI_DIAGNOSTICS_UNAVAILABLE` continues to block every case at the validity gate until the
  normalization is ratified and wired in. This was already true after ADR-0006; this ADR does not
  change that outcome, only makes clear what specifically remains before it can change.
- The sweep, once wired in, costs 6× the ensemble runtime per case (2 axes × 3 runs each, though the
  baseline run can be shared across axes, making it closer to 5×). Not evaluated for production
  latency in this ADR.

**Mitigation**
- The candidate normalization above gives whoever ratifies this ADR's follow-up a starting point
  rather than requiring them to invent one from nothing.
- `sensitivity.py`'s three-run-per-axis design shares the baseline run across both axes, so the
  actual cost is 1 baseline + 2 age + 2 forcing = 5 ensemble runs, not 6.
