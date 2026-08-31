# Track 2 Final Production Integration Report

**Run date:** 31 Aug 2026 · **Author:** router-datasets-55 · **Branch:** feat/netra-real-training

## 1. AIS SourceAdapter

- `EventAISAdapter` (`packages/varuna_integration/ais_source.py`, re-exported from
  `varuna_source_adapters/ais.py`) — real `SourceAdapter`, `fetch_with_mode()` maps
  `FetchResult.is_simulated` → `EvidenceMode.{REAL,SIMULATED}`; health-check failure or fetch
  exception → `EvidenceMode.UNAVAILABLE`, never inferred from class name/config/successful
  parsing (`tests/unit/test_ais_source_adapter.py`, 11/11 passing, including a real, non-skipped
  MC20 join test).
- `AISJoinStatus` distinguishes `TEMPORALLY_MATCHED` from `SPATIALLY_MATCHED_ONLY` —
  `tests/unit/test_track4_boundaries.py::test_spatial_candidacy_is_never_promoted_to_temporal_evidence`
  and `test_only_temporally_matched_counts_as_temporal_evidence` prove spatial proximity is never
  promoted into temporal evidence.
- Canonical MC20 path, real numbers (unchanged from the last real run, source unchanged):
  530 tracks total, 425 spatially matched, 320 temporally matched, 210 temporally unavailable;
  closest temporally-matched vessel MMSI `368181750` at 3.2554 km / +16m57s from SAR acquisition.

## 2. Evidence / Provenance

`evidence_mode`, `source`, `timestamp`, `provenance`, `case_id` verified to travel end to end:

| Component | Carries envelope? | Verified by |
|---|---|---|
| AIS | yes (`EventAISJoin`/adapter path) | `test_ais_source_adapter.py`, `test_real_ais_join.py` |
| ERA5 / CMEMS | yes (`ForcingCube.mode`) | `test_forcing_cube_validation.py`-equivalent + seam validation |
| PRATIVARTAN / PhiField | yes (`PhiField.envelope`, required) | `test_validity_gate.py`, production Phi report |
| NYAYA | yes (`AttributionResultV2.envelope`, required) | `test_validity_gate.py` |
| PRAVAAH | **yes, as of this pass** (`ForwardForecast.envelope`, ADR-0009) | `test_pravaah_mock.py`, `test_pravaah_cube_provider.py` (new tests) |

No component upgrades SIMULATED→REAL, UNAVAILABLE→REAL, or BLOCKED→VALID:
`tests/contract/test_evidence_mode.py` (12 tests: monotonic worsening, no config path assigns
REAL, CACHED_REPLAY cannot claim REAL) and the new
`test_forecast_envelope_is_simulated_even_when_input_envelope_claims_real` (a Mock provider
handed a REAL envelope still reports SIMULATED, closing the one gap found this pass — `derive()`
cannot force a *worse* mode than its input, so a mock must construct its own envelope rather than
derive one, which it previously did not do because it dropped the envelope parameter entirely).

## 3. Diffusivity Policy — ADR-0008

**Decision: A — diffusivity affects validity.** `SensitivityBlock.diffusivity_sensitivity` is a
required, non-`Optional` field computed by the identical procedure as `forcing_sensitivity`
(ADR-0007: "the same treatment as forcing"), and `dominant_assumption` already treats it as a
first-class candidate. The Validity Gate previously ignored it entirely. Now gated as a caveat
(non-blocking), threshold `0.7` reused from `forcing_sensitivity` (same scale/derivation, not
invented), reason code `EVIDENCE_INSUFFICIENT` (diffusivity ≠ forcing input). Full reasoning,
including why B and C were rejected, in `docs/adr/ADR-0008-diffusivity-sensitivity-gate-policy.md`.

Verified against the real MC20 production Phi result (not re-executed — reused per the
instruction not to redo proven work): `diffusivity_sensitivity=0.00107`, passes; gate verdict
unchanged (`DEGRADED`, `allows_operational_action=True`, sole caveat still `particle_loss`).

## 4. Production-Scale Phi Validation

Reused the existing 500-particle / 20-ensemble / 7-run sweep against real MC20 ERA5/CMEMS
(`reports/mc20_production_phi_sensitivity.json`, `mc20_production_phi_field.json`) — not
re-executed, per the instruction to preserve verified counts when the source is unchanged and not
redo already-proven work. Summary:

| Field | Value |
|---|---|
| particle_count / ensemble_count | 500 / 20 |
| runs | 7 (baseline, age±, forcing±, diffusivity±) |
| all runs completed | 20/20 ensemble members every run |
| convergence | 0.0440–0.0518, all `converged` |
| age_sensitivity | 0.0370 |
| forcing_sensitivity | 0.0051 |
| diffusivity_sensitivity | 0.0011 |
| weathering_sensitivity | None (no weathering model exists) |
| effective_radius_km | 102.92 |
| particle loss (baseline) | 42.7% (4273/10000) |
| evidence_mode | forcing=REAL, slick placeholder=SIMULATED, combined=SIMULATED |

Particle-loss dependence on `obs_time` and seed-cloud width fully characterized in prior
cross-session work (`docs/science/TRACK_2_FINAL_VALIDATION.md` §3) — not re-derived here.

## 5. Full Real Forcing Path

Real ERA5 (`sufficient`, 168×17×17) and real CMEMS (`sufficient`, 133×49×49) cubes flow through
`CubeBackedWindField`/`CubeBackedCurrentField` → PRATIVARTAN → PhiField with `overlap_hours=132.0`
— confirmed via `reports/mc20_track4_e2e_run.json`'s `forcing` stage (`status=produced,
evidence_mode=real`). No synthetic fallback anywhere in this stage; when NETRA returns no
detection, downstream stages correctly report `not_yet_produced`/`UNAVAILABLE` rather than
substituting synthetic geometry.

## 6. NYAYA / Validity — fail-closed proofs

`tests/unit/test_track4_boundaries.py` (30 tests, all passing) proves:
missing Φ → `NOT_SUPPORTED`/blocked downstream, never fabricated attribution; unknown/blocked
upstream never silently resolves to a passing state (`test_blocked_upstream_stays_blocked_downstream`,
`test_unknown_upstream_defaults_to_blocked`); simulated evidence can never be labelled real
(`test_simulated_provider_can_never_be_labelled_real`); spatial candidacy never promoted to
temporal evidence. `tests/unit/test_validity_gate.py` (17 tests after this pass) proves every gate
check in both directions. No threshold was weakened to make MC20 look successful — the real MC20
case correctly reports `NO_SLICK_DETECTED` and every downstream section correctly reports
`not_yet_produced`, not `VALID`.

## 7. PRAVAAH

`CubeBackedPravaahProvider` verified against a real current field: `forecast_drift()` derives its
output envelope from the caller's real input (REAL mode propagates end to end — new test
`test_real_forecast_propagates_real_evidence_mode_and_provenance`), `horizon_hours` recorded
directly on `ForwardForecast`, out-of-domain mid-trajectory freezes rather than extrapolates
(`test_out_of_domain_mid_trajectory_freezes_not_crashes`). No fabricated forecast values: drift is
computed from `velocity_at()` against the real gridded current field, not a hardcoded model
(contrast with `MockPravaahProvider`'s fixed drift+noise, now explicitly and unconditionally
marked `SIMULATED` regardless of its input, per ADR-0009).

## 8. ABHIYAN / Mission Interface

`test_abhiyan_full_gate_state_matrix` (new): VALID and DEGRADED → tasking permitted; RESTRICTED,
INCONCLUSIVE, and `gate_state=None` (the "UNAVAILABLE" case — no literal `ValidityState.
UNAVAILABLE` member exists) → zero taskings, no exception. `ValidityState.RESTRICTED`'s own
docstring ("analysis only — never reaches Action Gateway") is satisfied literally: zero taskings
is the contract-compliant realization of "informational/restricted," not a separate partial-
tasking type (none was invented).

## 9. Full Regression

`PYTHONPATH=packages pytest tests/unit tests/contract tests/integration tests/e2e -q`, run twice
this pass (once mid-flight through a peer's concurrent edit — see the transient noted in
`docs/track2/TRACK_2_FINAL_STATUS.md` — and once clean after this task's own commit landed):

**Final clean run: 576 passed, 10 skipped, 1 failed, in 342.27s.**

| Failure | Classification | Detail |
|---|---|---|
| `tests/unit/test_netra_training.py::test_netra_training_loop` — `TypeError: 'NetraSample' object is not subscriptable` (`packages/varuna_netra/training/trainer.py:250`) | **NETRA_RESOURCE / PRE_EXISTING** | NETRA-owned training-loop code, unrelated to Track 2, not touched — reproduces identically to the pre-existing baseline observed before this pass's changes. Not fixed, not suppressed, per the absolute constraint against touching NETRA training files. |

Zero Track-2 regressions from this pass's changes (diffusivity gate check, `ForwardForecast`
envelope). Skips (10) are pre-existing environment-gated skips (missing services/optional deps),
unaffected by this pass.

## 10. OperatorCase

`GET /v1/cases/{case_id}/operator-view` (`apps/api/operator_case_view.py`, peer-owned/actively
maintained this pass) serializes all required sections: origin, ais, attribution, validity,
forecast, decision (realizes "recommendation" — ABHIYAN's tasking output, gated on validity),
mission, alerts — confirmed via `reports/mc20_track4_operator_case.json`'s real MC20 run and
`tests/contract/test_operator_case.py` (19/19 passing). All missing states remain explicit
(`status="not_yet_produced"` with a concrete `reason` string at every stage, never an empty
silent success).

**Qualifier (raised by router-datasets-ca, verified here):** the artifact above validates the
*structural* claim, not a content one — `reports/mc20_track4_operator_case.json` is from the real
MC20 run, where only `ais` is actually populated; every downstream section is legitimately empty
with a named reason (NETRA returned no detection). This is in fact the more important case to
prove — the schema holding when producers correctly return nothing is exactly the fail-closed
property Task 6/9 require — but it does not by itself demonstrate populated content flowing
through every section simultaneously. The wording above was written to make only the structural
claim ("sections serialize," "missing states remain explicit") and was checked against this
qualifier before this report was finalized; no change to the finding was needed.

**Real provenance-rollup gap found and fixed by router-datasets-ca in response, credited here**
because it directly concerns this section's own subject: the same real-run artifact's top-level
`provenance` block (`artifact_ids`, `source_ids`, `model_versions`) was entirely empty — a
CaseWorkflow-produced case is unaffected (it registers PRAMAN artifacts), but a case produced by
the Track 4 pipeline shipped blank lineage despite each stage knowing its own source/version.
Fixed by having `case_bridge.py` collect `model_versions`/`source_ids` from what stages actually
reported and merging that into `_provenance()` rather than relying on the registry alone; absent
data stays empty rather than being invented (the simulated path correctly reports
`netra_detection: SIMULATED-no-model`, not a fabricated version string).
`processing_versions` remains deliberately `{}` — no code today versions how MC20 inputs were
normalized, a known, named, disclosed gap rather than a filled-in guess. Verified after the fix:
`tests/contract/test_operator_case.py` + `tests/integration/test_track4_mc20_e2e.py`, 46/46
passing.

## 11. Final MC20 Downstream Run

`reports/mc20_track4_e2e_run.json` (real, not re-run this pass — source and result unchanged):
real AIS (5 tracks, all `temporally_matched`), real ERA5/CMEMS forcing (`sufficient`/`sufficient`),
NETRA-v0.2-baseline returns `NO_SLICK_DETECTED` on 9 real tiles (a valid scientific outcome, not
altered, not worked around). Every downstream stage (Φ, attribution, validity, forecast, decision,
mission, alerts) correctly reports `not_yet_produced` with an explicit upstream-chained reason.
Track 2 demonstrates correct downstream handling of a real null NETRA result — the objective of
this task — without fabricating a detection to exercise the rest of the chain.

## Real/Synthetic Path Matrix (updated this pass)

| Component | Real path | Simulated path | Silent fallback? |
|---|---|---|---|
| AIS | `EventAISAdapter` | none (adapter fails closed to UNAVAILABLE) | No |
| ERA5/CMEMS | `Cube*Field` from real `ForcingCube` | none in production path | No |
| PRATIVARTAN/Φ | real ensemble on real forcing | `slick_placeholder` always marked SIMULATED | No — combined envelope worsens to SIMULATED honestly |
| PRAVAAH | `CubeBackedPravaahProvider` | `MockPravaahProvider` — **now hardcoded SIMULATED regardless of input (ADR-0009 fix)** | No, closed this pass |
| CHHAYA | none implemented | stub, hardcoded, **now marked SIMULATED (side effect of ADR-0009)** | No, closed this pass |

**Verdict: no code path silently claims fabricated data is real**, including the one gap
(PRAVAAH/CHHAYA envelope-dropping) found and closed during this pass.

## Scientific Limitations

- PRAVAAH is implemented and evidence-correct but not yet invoked by `CaseWorkflow`.
- `diffusivity_sensitivity`'s gate threshold (`0.7`) is reused from `forcing_sensitivity` by
  documented analogy, not independently calibrated for the diffusivity axis specifically.
- `particle_loss` on a synthetic-placeholder-seeded run conflates a physical land-blocked fraction
  with a seed-cloud-width artefact (documented previously, unchanged this pass).
- CHHAYA's forecast stub is a hardcoded placeholder unrelated to Track 2's own scope; only its
  now-mandatory evidence field was touched.

## Safety

```
deleted=0
moved=0
renamed=0
overwritten=0
NETRA modified=0
NETRA checkpoint modified=0
NETRA Gold modified=0
MC20 modified=0
official test modified=0
```

## FINAL STATUS

**TRACK_2_COMPLETE_AND_FROZEN**

## FINAL NEXT ACTION

None executed. For a future, separately-mandated phase: wire PRAVAAH into `CaseWorkflow`;
independently calibrate the diffusivity sensitivity threshold once enough real perturbation runs
exist to justify a number distinct from `forcing_sensitivity`'s; consider a land-mask-aware
particle-loss metric that separates the physical asymptote from seed-geometry artefacts. Do not
start any of these without a new explicit mandate — Track 2 is frozen as of this report.
