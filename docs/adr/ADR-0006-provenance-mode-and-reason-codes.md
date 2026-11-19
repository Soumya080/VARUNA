# ADR-0006 — EvidenceMode, Monotonic Provenance, and Gate Reason Codes

**Status:** Accepted · **Date:** 29 Aug 2026

## Context

`TrustState` answers "how much should this influence a decision?" — a question about the
source's reliability. It does not, and was never meant to, answer a different question
that the system needed to answer honestly before any real-vs-synthetic claim could be
trusted: **is this evidence a measurement of the real world, a stand-in for one, or
absent entirely?**

Before this ADR, that question had no first-class answer anywhere in the contract layer.
`is_simulated: bool` existed in exactly two unrelated dataclasses
(`varuna_source_adapters.protocol.FetchResult`, `varuna_alerts.protocol.DeliveryResult`)
and reached neither `EvidenceEnvelope`, `PhiField`, nor `AttributionResultV2`. The
practical consequence: `PrativartanService.reconstruct_origin` built a fresh envelope with
`Provenance(source_id="synthetic")` but `trust=TRUSTED` (the default) and no signal
anywhere that the data was synthetic, and `ValidityService.evaluate` unconditionally
hardcoded `source_trust=TrustState.TRUSTED` regardless of what actually produced the
input. A fully synthetic, entirely fabricated pipeline run and a real one were
indistinguishable at the validity gate. That is disqualifying for a system whose output
is meant to inform an operational decision.

A second, compounding problem: six of the nine validity-gate checks read `PhiDiagnostics`
fields that were hardcoded literals (`convergence=0.05`, `particles_lost=0`,
`runtime_seconds=1.0`, a `SensitivityBlock` of all `0.1`s) rather than anything computed
from the ensemble. Hardening the gate's *policy* while its *inputs* were fabricated would
have been decoration, not hardening.

A third, smaller problem: the gate's failure reasons were free-text English sentences
(`"Origin field did not converge"`) with no machine-readable classification, so nothing
downstream — an API response, an alert policy, a test — could branch on *why* the gate
failed without string-matching prose.

## Decision

### 1. `EvidenceMode`

```python
class EvidenceMode(StrEnum):
    REAL = "real"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"

    @property
    def rank(self) -> int:
        return {"real": 0, "simulated": 1, "unavailable": 2}[self.value]
```

`EvidenceEnvelope.mode: EvidenceMode` is **required, with no default**. A missing value is
a construction error, by design — every producer must explicitly declare which of the
three it is emitting. This is the same pattern already used for `provenance`.

**The central rule, and the reason this needed an ADR:**

> EvidenceMode can only **worsen** as evidence flows downstream, never improve.
> `REAL → SIMULATED → UNAVAILABLE` is the only direction of travel. No code path — and in
> particular no configuration flag, settings object, or environment variable — may
> construct or derive a SIMULATED or UNAVAILABLE input into a REAL output.

This mirrors the existing monotonic-degradation pattern for `trust`, `validity_state`, and
`degradation_state` in `EvidenceEnvelope.derive()` (see ADR-0002), extended to a fourth
axis that none of the existing three actually captured: TrustState is about *reliability*,
ValidityState is about *actionability*, DegradationState is about *completeness* — none of
them is about *is this real*.

### 2. Structural enforcement, not convention

- `derive()` computes `derived_mode = max((e.mode for e in inputs), key=lambda m: m.rank)`
  over `self` and every envelope in `also_from`. **There is no `mode=` parameter on
  `derive()`** — unlike `validity=`/`degradation=`, which a caller may push further down
  but never up, there is no legitimate reason for a caller to touch mode at all. This is
  checked structurally in `tests/contract/test_evidence_mode.py` via
  `inspect.signature(EvidenceEnvelope.derive)` — the parameter cannot exist, not merely
  "should not be misused."
- A `@model_validator` on `EvidenceEnvelope` rejects the combination
  `mode=REAL` + `degradation_state=CACHED_REPLAY`. A cached/offline replay (DEMO_MODE) is,
  by construction, not a live real-world measurement — it is a recording of one played
  back later. SIMULATED or UNAVAILABLE may freely carry `CACHED_REPLAY`; REAL may not.
- `tests/contract/test_evidence_mode.py::test_no_settings_or_config_reference_assigns_mode_real`
  statically scans every `mode=` assignment site under `varuna_contracts`,
  `varuna_prativartan`, `varuna_nyaya`, and `varuna_source_adapters` via `ast.walk` and
  fails if any right-hand side references `settings`, `os.environ`, or `getenv`. This
  inspects actual code paths, not comments — a future contributor cannot quietly wire a
  feature flag into `mode=` without this test catching it.

### 3. Where mode comes from today

Three accepted origins, none of them config:

1. A real source adapter's `FetchResult.is_simulated=False` → `EvidenceMode.REAL`
   (translation point established, not yet wired into every adapter — see Remaining P1).
2. A mock/synthetic provider explicitly constructing `mode=EvidenceMode.SIMULATED` — every
   test fixture, mock, and `PrativartanService.reconstruct_origin`'s default (no real
   forcing pipeline exists yet; that default is an honest reflection of current systemic
   reality, not a value read from settings).
3. An explicit `EvidenceMode.UNAVAILABLE` for a path that determined no evidence exists —
   established as a value the type system can carry; no producer emits it yet in this
   tranche (AIS/forcing unavailability is Tranche 2/3 work).

### 4. `GateReason`

```python
class GateReason(StrEnum):
    DATA_INVALID
    DATA_QUARANTINED
    EVIDENCE_INSUFFICIENT
    EVIDENCE_SIMULATED
    PHI_NOT_CONVERGED
    PHI_UNINFORMATIVE
    PHI_DIAGNOSTICS_UNAVAILABLE
    ATTRIBUTION_UNCERTAIN
    ATTRIBUTION_NOT_DISTINGUISHABLE
    FORCING_INSUFFICIENT
    TEMPORAL_JOIN_UNAVAILABLE
    ACTION_NOT_AUTHORIZED
```

`GateCheck.reason_code: GateReason | None = None` — defaulted, so every existing
`extra="forbid"` consumer that constructs a `GateCheck` without this field keeps working.
The free-text `detail` field is unchanged and still carries the officer-facing sentence;
`reason_code` complements it for machine consumption. Not every enum member is emitted by
the gate implemented in this tranche — `TEMPORAL_JOIN_UNAVAILABLE` and
`ACTION_NOT_AUTHORIZED` belong to checks a later tranche implements (the AIS temporal join,
and mission authorization respectively) and are defined now so that work does not require
a second ADR.

### 5. Φ diagnostic optionality — honest, not fabricated

`PhiField.sensitivity` changes from a required `SensitivityBlock` to `SensitivityBlock |
None`. This is the **only** field made optional. `PhiDiagnostics`'s own fields
(`particles_lost`, `runtime_seconds`, `convergence`, `n_modes`, `multimodal`,
`boundary_interaction`) remain required and are now genuinely computed from the ensemble
output in `phi_builder.py` (see that file for the exact statistics — a split-ensemble
divergence for `convergence`, non-finite particle counts for loss, connected-component
labeling of the built field for `n_modes`) rather than literals. A real sensitivity sweep
(re-running the ensemble under perturbed age/forcing assumptions) is out of scope for this
tranche and tracked as P1; until it exists, reporting a number would be fabrication, so the
field is honestly `None` and the validity gate treats that as a **blocking**
`PHI_DIAGNOSTICS_UNAVAILABLE` condition rather than silently passing on a manufactured
`0.1`.

### 6. Contract compatibility

- `GateCheck.reason_code` has a default → existing constructors unaffected.
- `EvidenceEnvelope.mode` has **no** default → every existing construction site across the
  repository required a `mode=` addition. This was mechanical (test fixtures and mocks all
  became `EvidenceMode.SIMULATED`, matching what they always were) and is the intended
  effect of Phase 4: a missing declaration should be impossible to construct around, not
  quietly defaulted away.
- `PhiField.sensitivity` becoming `Optional` is backward compatible for readers (a
  consumer that never handled `None` before now must, and the validity gate is the one
  consumer that does).

## Consequences

**Positive**
- "Is this real" is now a first-class, structurally-enforced question with the same
  monotonic-degradation guarantee the envelope already gave trust/validity/degradation.
- The validity gate's failures are now machine-classifiable without string matching.
- Six previously-fabricated Φ diagnostics are now real computed statistics; the two that
  cannot yet be computed honestly (`SensitivityBlock`'s two fields) block rather than lie.
- A fully synthetic run can no longer silently present as `VALID`/real at the gate.

**Negative**
- Every `EvidenceEnvelope` construction site in the repository needed a mechanical
  `mode=` addition — a one-time cost, paid in this tranche.
- The gate is currently *more* likely to report `RESTRICTED` than before, because missing
  `SensitivityBlock` is unconditionally blocking. `tests/regression/test_golden_cases.py`
  was updated accordingly — the change reflects the gate now failing closed on genuinely
  missing diagnostics, not a regression in attribution itself.
- `PratiConfig.convergence_threshold` (0.15, previously defined but unused) is now load-
  bearing for the `convergence` computation; changing it changes gate behavior.

**Mitigation**
- The sensitivity sweep is the natural P1 follow-up that removes the current
  always-blocking state once implemented for real.
- `EvidenceMode.SIMULATED` is a **caveat**, not a block, specifically so the deterministic
  synthetic E2E integration test can still execute end to end while remaining honestly
  labeled — see `tests/e2e/test_m4_full_pipeline.py` and its Tranche 2+ successor.
