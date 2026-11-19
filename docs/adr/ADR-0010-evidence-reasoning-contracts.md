# ADR-0010 — Evidence, Uncertainty, Hypothesis and Action Contracts

**Status:** Accepted · **Date:** 1 Sep 2026

## Context

`varuna_contracts` is a locked package: its module docstring requires an ADR
for any change. The product-build phase needed four new cross-subsystem types
that no existing contract covered, and putting them anywhere else would have
made them subsystem-private — defeating the purpose, since the whole point is
that CHHAYA, NYAYA, the agentic layer and the operator view all speak the same
vocabulary.

The driving product principle: **NETRA is not the final oracle.** Before this
ADR the system had no type in which a detection could exist as *evidence*
rather than as a verdict. `SlickDetection` carries a classification and a
confidence and nothing that qualifies them — no OOD assessment, no
preprocessing identity, no limitations list. A consumer holding a
`SlickDetection` has no structural reason not to treat it as ground truth.

## Decision

Four new modules in `varuna_contracts`, all additive. No existing type changed.

### 1. `detection_evidence.py` — `DetectionEvidenceEnvelope`, `Measured`, `UncertaintyAssessment`

`DetectionEvidenceEnvelope` deliberately has **no verdict field**.
`classification`/`confidence` are recorded as the detector's own claims, sat
next to `ood_risk`, `limitations`, `preprocessing_version` and
`channel_binding` — the things that stop those claims being read as truth.

**`Measured` is the load-bearing idea.** Every quantity that could plausibly
be fabricated is a `Measured`, pairing a value with a `MeasurementStatus`
(MEASURED / INFERRED / SIMULATED / REPLAYED / UNAVAILABLE). Two validators
make dishonesty unrepresentable rather than merely discouraged:

- `UNAVAILABLE` with a value → rejected.
- any other status with `value=None` → rejected.

`MeasurementStatus` is deliberately **distinct from `EvidenceMode`**.
`EvidenceMode` describes the *input data*; `MeasurementStatus` describes *this
particular number*. A REAL-mode run can carry INFERRED quantities (a
morphology summary derived from a real mask); a SIMULATED run can carry
MEASURED ones (genuinely measured off synthetic input). Collapsing them would
lose the distinction operators need.

`UncertaintyAssessment` is component-level by construction — model confidence,
data quality, OOD risk, evidence agreement, conflict count, attribution and
forecast uncertainty are separate fields with no aggregate score. There is
deliberately no `overall_confidence`: a single scalar destroys the information
needed to decide *what to do* about the uncertainty. `dominant_concern` names
the limiting component instead of scoring it.

### 2. `source_hypothesis.py` — `SourceHypothesisEnvelope`

CHHAYA's output. Separate from NYAYA's `AttributionResultV2` because they
answer different questions: NYAYA asks "which *vessel*", CHHAYA asks the prior
question "what *kind of source* is this at all". Conflating them would allow a
confident vessel attribution on a slick whose most likely source class is a
natural seep.

`method: HypothesisMethod` and `methodology_note: str` are **required**. This
is the honesty mechanism: a deterministic rule engine cannot be rendered as a
learned model, because every envelope carries `DECLARED_LIKELIHOOD_RATIO` and
a note stating it is uncalibrated. A validator also rejects posteriors that do
not sum to 1.0 and rejects an empty hypothesis list — "we don't know" must be
expressed as `UNKNOWN` at 1.0, not as an absence.

**Module naming note:** this module was briefly called `hypothesis.py`, which
shadowed the `hypothesis` testing library on `sys.path` and broke collection
for the entire test suite. Renamed to `source_hypothesis.py`. Any future
contracts module must not take the name of an installed top-level package.

### 3. `action.py` — `NextBestAction`, `ActionRecord`, `DecisionTrace`

The agentic layer's vocabulary. `NextBestAction.because` and
`targets_uncertainty` are required: an action is selected because a *named*
piece of evidence is missing, weak or contradictory, never because an
unexplained score crossed a threshold. `DecisionTrace.render()` exists so the
question "why is this case in this state?" is answerable without reading source.

`ActionKind` is small and concrete — each member maps to a capability that
actually exists in the repository, so the loop cannot propose an action
nothing can execute.

## Consequences

**Positive**
- Detection results can be consumed as evidence, with their limitations
  attached, rather than as verdicts.
- Fabricated numbers are structurally hard: `Measured` rejects both directions
  of value/status mismatch.
- A future learned CHHAYA can replace the engine behind
  `SourceHypothesisEnvelope` without touching a single caller.

**Negative / residual**
- Four new modules in a locked package is a meaningful surface increase; each
  is additive and none alters an existing type, but the package is larger to
  reason about.
- `Measured` is more verbose at construction than a bare float. That verbosity
  is the point, but it is a real ergonomic cost at every call site.
- `UncertaintyAssessment` has no aggregate score, so any UI wanting a single
  headline number must choose and justify its own reduction. This is
  deliberate; it is also work pushed onto consumers.

## Not done

- No change to `SlickDetection`, `EvidenceEnvelope`, `PhiField`,
  `AttributionResultV2`, or `ValidityGateResult`.
- No `HypothesisMethod.LEARNED_MODEL` implementation — the member is reserved
  so the contract does not need reopening later; nothing produces it today.
- No aggregate confidence score, deliberately (see above).
