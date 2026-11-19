# ADR-0009 — `ForwardForecast` Carries an `EvidenceEnvelope`

**Status:** Accepted · **Date:** 31 Aug 2026

## Context

Track 2 final production integration (Task 7 — PRAVAAH) required verifying
that a real current field driving a drift forecast records source, evidence
mode, validity, provenance, and time horizon. Auditing `PravaahProvider`
(`packages/varuna_pravaah/protocol.py`) found:

- `forecast_drift(slick, forcing_path, horizon_hours, envelope)` already
  **receives** an `EvidenceEnvelope` on every call, in both
  `MockPravaahProvider` and `CubeBackedPravaahProvider`.
- Neither implementation **did anything with it.** The parameter was
  accepted and never read. `ForwardForecast`
  (`packages/varuna_contracts/schemas.py`) had no `envelope` field, no
  `evidence_mode`, no `provenance` — there was nowhere for the value to go
  even if a provider had wanted to record it.
- `packages/varuna_chhaya/inference.py::ChhayaInferenceService.forecast()`
  (a separate, non-Track-2 subsystem's stub) had the identical gap: a
  hardcoded, entirely fabricated `ForwardForecast` with no evidence marker
  at all.

This is a real instance of Task 2's concern ("evidence mode, source,
timestamp, provenance, case_id must travel through the complete case") not
being met for one specific artifact type, `ForwardForecast` — every other
major artifact in the system (`PhiField`, `AttributionResultV2`,
`ValidityGateResult`) already carries a required `envelope: EvidenceEnvelope`
field (`packages/varuna_contracts/phi.py`, `decision.py`). `ForwardForecast`
was the one artifact type in the case chain missing it.

## Decision

**Add `envelope: EvidenceEnvelope` to `ForwardForecast`**, required, no
default — the identical field, identical requiredness, as the three
existing precedents. This is not a new pattern; it closes `ForwardForecast`
onto a pattern already established elsewhere in the same contracts package.

**Wire both PRAVAAH providers and the CHHAYA stub to populate it**, with a
distinction that matters:

- **`CubeBackedPravaahProvider`** (real): `envelope.derive(artifact_id=...,
  produced_by="pravaah_cube_provider", model_version=...)`. It genuinely
  operates on the caller-supplied real current field, so deriving from the
  caller's envelope (monotonic-worsening-only, per ADR-0006) is correct —
  a REAL input envelope yields a REAL forecast envelope; a SIMULATED or
  degraded input correctly worsens the output.

- **`MockPravaahProvider`** (fabricated): does **NOT** call `.derive()` on
  the caller's envelope. It constructs a **fresh** `EvidenceEnvelope` with
  `mode=EvidenceMode.SIMULATED`, hardcoded, unconditionally. Reasoning:
  `.derive()` has no mechanism to force mode to a *worse* value than the
  worst input (ADR-0006 deliberately removed any `mode=` override) — it can
  only take the max of what it's given. If a caller ever passed a REAL-mode
  envelope into this Mock provider (e.g. a case that has real AIS/forcing
  but falls back to the mock forecaster for some other reason), naively
  deriving would let a forecast built from a fixed northeast-drift-plus-noise
  model with no physics inherit a REAL claim. A mock provider is the
  *originating* producer of synthetic data — the same category ADR-0006
  already handles at the `SourceAdapter` boundary by hardcoding
  `is_simulated=True` → `EvidenceMode.SIMULATED` rather than deriving it.
  This ADR applies the identical treatment here. Lineage is still preserved
  via `parent_artifact_ids=[envelope.artifact_id]` and `case_id` is still
  carried through — only `mode` is forced rather than derived.

- **`ChhayaInferenceService.forecast()`** (CHHAYA, not Track 2, but a
  consumer of the now-required field): same treatment as the PRAVAAH mock —
  a fresh, hardcoded-`SIMULATED` envelope, since the method is a hardcoded
  placeholder unconditionally (`forecast_id="forecast_1"`,
  `trajectory_path="mock_path"`, ignores `current_data` entirely). Not
  touching CHHAYA's logic — only satisfying the newly-required contract
  field honestly.

## Consequences

**Positive**
- `ForwardForecast` now matches the rest of the artifact chain: every major
  case artifact from AIS through PRAVAAH carries `envelope`.
- A concrete regression is now impossible to reintroduce silently: a Mock
  provider handed a REAL envelope cannot make its fabricated output claim
  REAL (`tests/unit/test_pravaah_mock.py::
  test_forecast_envelope_is_simulated_even_when_input_envelope_claims_real`).
- `apps/api/operator_case_view.py`'s forecast section already reads
  `evidence_mode` off whatever payload it is handed
  (`_mode_of(payload)`) — no change needed there; it now has a real value to
  read once PRAVAAH is wired into `CaseWorkflow` (a separate, already-known,
  disclosed gap — see docs/science/TRACK_2_FINAL_VALIDATION.md — this ADR
  does not close that wiring gap, only the envelope-plumbing gap upstream of
  it).

**Negative / residual**
- `envelope` being required (no default) means every existing
  `ForwardForecast(...)` construction site had to be updated in the same
  change (`packages/varuna_pravaah/{mock,cube_provider}.py`,
  `packages/varuna_chhaya/inference.py`, `tests/unit/test_whatif.py`). All
  sites were found by repo-wide search and updated; none were missed
  (verified by running the full affected test set green).
- Any external caller serializing an old, pre-ADR-0009
  `ForwardForecast` JSON blob without an `envelope` key will now fail
  `model_validate`. No such blob exists in this repository today (PRAVAAH
  is not yet wired into `CaseWorkflow`, so no case has ever persisted a
  `ForwardForecast` to storage) — confirmed by inspection, not asserted.

## Not done

- `CaseWorkflow` still does not call PRAVAAH at all — this ADR does not wire
  that integration. It only ensures that whenever PRAVAAH *is* invoked
  (directly, as in `scripts/mc20_production_validity_gate.py`-style
  callers, or once wired), its output honestly carries evidence provenance.
- No change to PRAVAAH's forecasting physics (advection, landfall
  detection) — plumbing only.
