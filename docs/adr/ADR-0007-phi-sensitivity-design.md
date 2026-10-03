# ADR-0007 — Φ Sensitivity Sweep Design

**Status:** Accepted (amended) · **Date:** 29 Aug 2026 (normalization ratified same day)

**Amendment note:** the "one genuinely open decision" this ADR originally left unresolved — how to
convert a measured field difference into `SensitivityBlock`'s `[0, ...)` displacement scale — has
been ratified below (see "Normalization, ratified"). A second, related gap surfaced during
implementation and is resolved in the same amendment: `SensitivityBlock.weathering_sensitivity` is
now `float | None`, because no weathering model exists anywhere in PRATIVARTAN
(`PhiField.weathering_model` is always `None`) and there was nothing for a sweep to honestly
perturb on that axis. `age_sensitivity`, `forcing_sensitivity`, and a newly-added
`diffusivity_sensitivity` (using `PratiConfig.diffusivity_range`'s existing bounds, the same
treatment as forcing) are all real, computed, non-fabricated values as of this amendment.

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

2. **Ratified in this amendment (`build_sensitivity_block()`, same module):** the conversion from
   `SensitivitySweepResult`'s raw centroid shifts into `SensitivityBlock`'s `age_sensitivity`/
   `forcing_sensitivity`/`diffusivity_sensitivity` — see "Normalization, ratified" below for the
   reasoning. `phi_builder.build_phi_field()`'s default (cheap, 1-run) path still leaves
   `PhiField.sensitivity = None`, by design — the sweep costs 7x the runtime, so it is only computed
   by callers that explicitly invoke `PrativartanService.reconstruct_origin_with_sensitivity()`.
   `weathering_sensitivity` remains genuinely unavailable (see below) — its `None` is not a
   placeholder pending ratification, but the honest state of a physical process this codebase does
   not model at all.

**Ratified in this amendment** (see "Normalization, ratified" below): divide the perturbed field's
centroid shift by an effective radius derived from the *baseline* field's own
`effective_support_km2` (`radius_km = sqrt(effective_support_km2 / pi)`), **not clipped** — the
contract has no upper bound on these fields, so a shift larger than the field's own radius is
reported as a real value above 1.0, not truncated.

## Normalization, ratified

Re-reading `SensitivityBlock`'s own field constraint resolves the ambiguity the original ADR text
raised. `age_sensitivity`/`forcing_sensitivity`/`diffusivity_sensitivity` are declared
`Field(..., ge=0)` — **there is no upper bound in the contract.** The docstring's "1 = the field
moves by its own effective radius" is a reference point for interpreting the number, not a ceiling
the type enforces. That removes the objection that motivated hedging toward a saturating
divergence-based measure (which was the actual source of the "no consensus" claim in the original
text) — a non-saturating, continuous ratio was never excluded by the contract; it only looked
excluded because the earlier draft assumed a `[0, 1]` cap that isn't actually there.

With that resolved, the docstring specifies the formula in words already: **displacement, measured
in units of the field's own effective radius.** Two quantities already exist to instantiate this
literally, with no free parameter beyond a geometric identity:

- **Displacement:** the centroid shift already measured by `run_sensitivity_sweep()` (mass-weighted
  lon/lat centroid of the spatial marginal, before vs. after perturbation) — a continuous distance
  in km, not a saturating one.
- **The field's own radius:** `effective_support_km2` (already honestly computed since ADR-0006 —
  "area holding 90% of mass") converted to a circular-equivalent radius via `r = sqrt(A / pi)`. This
  is the standard area-to-radius identity for a circle; `pi` is not a tunable scientific assumption.

`sensitivity = centroid_shift_km / effective_radius_km`. A shift equal to the field's own radius
scores exactly `1.0` — the literal reading of the docstring. A shift ten times the radius scores
`10.0` — a real, reportable value, not clipped, because nothing in the contract requires clipping.

The originally-floated alternative (an entropy- or divergence-based measure) is not actually a
competing reading of the same question: entropy/divergence characterize the field's **shape**
(concentration, multimodality — already captured by the separate `entropy`/`concentration`/`n_modes`
diagnostics), not its **position**. The docstring's verb is "moves" — a positional claim. There is no
second existing contract field that would give a coherent alternative "moved by" quantity, so this
is not a case of two equally-defensible readings requiring a science-lead tiebreak; it is the unique
operationalization available from what the contract already defines.

**Residual imprecision, reported rather than hidden:** the age axis perturbs by exactly `±
age_prior_std_hours`, a literal 1-sigma value, matching the docstring precisely. The forcing and
diffusivity axes instead pin `PratiConfig.current_noise_range`/`diffusivity_range` to their existing
*uniform-sampling* bounds — a reuse of an existing, already-decided range, but not a literal Gaussian
1-sigma in the way the age axis is. This is disclosed, not glossed over; it does not block
ratification because the ranges themselves are pre-existing project decisions, not invented here.

`weathering_sensitivity` has no ratified value and none is invented: `SensitivityBlock.
weathering_sensitivity` is widened to `float | None`, and `build_sensitivity_block()` always returns
`None` for it. This stays open until PRATIVARTAN has a weathering model to perturb — a physics
implementation task, not a normalization question, and explicitly out of scope for this ADR.

## Consequences

**Positive**
- The mechanical sweep and the normalization are both real, tested (`tests/unit/
  test_phi_sensitivity_sweep.py` — IMPLEMENTATION SMOKE; `tests/unit/test_sensitivity_normalization.py`
  — direct fixture-based coverage of low/medium/high/boundary/missing/invalid/monotonicity/
  determinism), and reuse only parameters and metrics that already existed before this ADR —
  nothing here is a new scientific assumption.
- A real case run through `PrativartanService.reconstruct_origin_with_sensitivity()` →
  `NyayaService.attribute()` → `ValidityService.evaluate()` confirmed the `phi_diagnostics_
  availability`/`PHI_DIAGNOSTICS_UNAVAILABLE` check no longer appears at all once sensitivity is
  populated, and the `age_sensitivity`/`forcing_sensitivity` checks run against real (non-fabricated)
  numbers instead.
- `SensitivityBlock` staying required for its three real axes (and `None` only for the genuinely
  unmodeled weathering axis) keeps the gate honest in both directions — a wrong-but-confident number
  would have been worse than blocking, and blocking forever on a question that was actually already
  answerable by the existing contract would have been worse than ratifying it.

**Negative**
- The sweep costs 7× the ensemble runtime per case (1 baseline + 2 age + 2 forcing + 2 diffusivity;
  the baseline run is shared across all three axes, so it is 7 runs total, not 3×3-1). This is why
  `reconstruct_origin_with_sensitivity()` is a separate, explicitly opt-in method — every existing
  caller of `reconstruct_origin()` is unaffected and keeps the cheap 1-run cost with sensitivity=None.
- The forcing/diffusivity axes are not a literal Gaussian 1-sigma perturbation the way the age axis
  is (see "Residual imprecision" above) — a real but disclosed imprecision.
- `weathering_sensitivity` remains permanently `None` until a weathering model exists in PRATIVARTAN
  at all; this ADR does not change that.
- Production-scale execution (500 particles × 20 ensemble members × 7 runs) has not been performed —
  only small-fixture IMPLEMENTATION SMOKE and direct-fixture normalization tests, per this session's
  resource-safety constraint (NETRA training active on the same GPU throughout).

**Mitigation**
- `build_sensitivity_block()` raises rather than fabricates when the baseline field is degenerate
  (zero effective support), consistent with every other honesty mechanism in this project.
- The validity gate's existing 0.7 thresholds for age/forcing sensitivity are unchanged by this ADR —
  no new operational threshold was invented; only the number they are compared against went from
  nonexistent to real.
