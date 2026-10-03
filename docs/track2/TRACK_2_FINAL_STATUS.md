# Track 2 — Final Status

**Date:** 31 Aug 2026 · **Scope:** PRATIVARTAN, Φ reconstruction/sensitivity, NYAYA, Validity
Gate, PRAVAAH, ABHIYAN interface, AIS evidence boundary, EvidenceMode/provenance propagation.

**NETRA status during this work:** training active in a concurrent session (GPU 100% util
observed at start). No NETRA training file, checkpoint, or Gold dataset was read for
modification or written to at any point in this pass. All new/changed work in this pass is
CPU-only (contract/pydantic edits, gate logic, unit tests, a re-run of an already-saved Phi
result through the gate — no ensemble re-execution).

---

## Seam status (already verified in prior sessions, re-confirmed here, not re-derived)

| Seam | Status |
|---|---|
| real ERA5 → CubeBackedWindField | READY (re-confirmed via passing `tests/unit/test_cube_field.py`, `test_era5_reader`-equivalent coverage) |
| real CMEMS → CubeBackedCurrentField | READY |
| both → PRATIVARTAN → PhiField | READY |
| PhiField → NYAYA → ValidityGate | READY, extended this pass (diffusivity check) |
| ValidityGate → ABHIYAN | READY, extended this pass (full 5-state matrix test) |
| real current field → PRAVAAH | READY, extended this pass (evidence envelope now recorded) |
| EvidenceMode monotonicity | READY (`tests/contract/test_evidence_mode.py` — 12 tests, unchanged, still green) |

---

## This pass's findings and changes

### Task 3 — Diffusivity policy: **A. Diffusivity affects validity**

`SensitivityBlock.diffusivity_sensitivity` was computed by ADR-0007 (required field, `Field(...,
ge=0)`, same normalization and derivation procedure as `forcing_sensitivity`) but the Validity
Gate never read it — a real, always-populated diagnostic was invisible to both the gate and the
officer. See `docs/adr/ADR-0008-diffusivity-sensitivity-gate-policy.md` for the full evidentiary
argument. Resolution: gated as a caveat (non-blocking, matching `age_sensitivity`'s severity),
reusing the existing `0.7` threshold (same scale/derivation as `forcing_sensitivity`, not a new
number), reason code `EVIDENCE_INSUFFICIENT` (not `FORCING_INSUFFICIENT` — diffusivity is a
transport parameter, not a forcing input). Re-verified against the saved MC20 production Phi
result: `diffusivity_sensitivity=0.0011`, passes cleanly, gate verdict (`DEGRADED`, same
`particle_loss` caveat) unchanged.

### Task 7 — PRAVAAH: evidence envelope was silently dropped

Both `PravaahProvider` implementations accepted an `EvidenceEnvelope` parameter on every call and
never used it; `ForwardForecast` had no field to carry evidence mode, source, or provenance at
all. See `docs/adr/ADR-0009-forward-forecast-evidence-envelope.md`. Resolution: `ForwardForecast`
gained a required `envelope: EvidenceEnvelope` field (matching the existing pattern on
`PhiField`/`AttributionResultV2`/`ValidityGateResult`). `CubeBackedPravaahProvider` derives from
its real input envelope (correct — it operates on real forcing). `MockPravaahProvider` — and, as
a side effect of the same required field, the unrelated CHHAYA stub
(`ChhayaInferenceService.forecast`) — construct a **fresh**, hardcoded-`SIMULATED` envelope rather
than deriving, because `derive()` can only worsen mode and a mock/stub is itself the originating
producer of fabricated data (same category `SourceAdapter` mocks already handle by hardcoding
`is_simulated=True`). A new regression test proves a Mock handed a REAL-mode input still reports
SIMULATED output.

### Task 8 — ABHIYAN: full gate-state matrix now explicitly tested

`AbhiyanService.plan_mission()` was already correct: `ValidityState.allows_operational_action`
gates a binary decision (VALID/DEGRADED → provider generates tasking; RESTRICTED/INCONCLUSIVE/
`gate_state=None` → empty tasking list, no exception, no partial dispatch).
`ValidityState.RESTRICTED`'s own docstring ("analysis only — never reaches Action Gateway") is the
authoritative definition of the master-prompt's "informational/restricted recommendation" —
producing zero taskings, not a distinct partial-tasking object, is the contract-compliant reading;
inventing a new partial-tasking type was not done (would be a `varuna_contracts` addition with no
existing basis). Added `test_abhiyan_full_gate_state_matrix` covering all five inputs
explicitly (there is no literal `ValidityState.UNAVAILABLE` — `gate_state=None` is the
equivalent case and is proven to be treated identically to blocking, not permissively).

### Tasks 1, 2, 4, 5, 6, 10, 11 — reused, not re-derived

Per the master prompt's own instruction not to redo already-proven work: the real AIS boundary
(`EventAISAdapter`, `fetch_with_mode`, canonical MC20 join — 530 tracks, 320 temporally matched),
EvidenceMode monotonicity, the production-scale Φ sensitivity sweep (500 particles × 20 ensemble
× 7 runs against real MC20 ERA5/CMEMS), the real forcing path (`sufficient`/`sufficient`
ERA5/CMEMS status, no synthetic fallback), NYAYA/Validity fail-closed proofs
(`tests/unit/test_track4_boundaries.py`, 30 tests), the OperatorCase endpoint (8 required
sections present: origin, ais, attribution, validity, forecast, decision [functions as the
required "recommendation"], mission, alerts), and the full MC20 downstream run (real AIS +
real ERA5/CMEMS forcing, NETRA returns `NO_SLICK_DETECTED` — correctly propagated as
`not_yet_produced` with an explicit reason through every downstream stage, not altered, not
worked around) were all already implemented, tested, and passing from prior sessions (this one
and peer sessions on the same branch). This pass re-ran the relevant test files to confirm they
are still green (they are) rather than re-executing already-proven work.

### Task 9 — Full regression

See `reports/track2/TRACK_2_FINAL_REPORT.md` for the final counts. One transient false-failure
batch was observed and diagnosed during this pass: a background regression run captured a
mid-flight edit by a peer session actively landing an `OperatorCase.recommendation` field
(`apps/api/operator_case_view.py`, `packages/varuna_contracts/operator_case.py`) — 12
`test_operator_case.py` failures and 5 `test_track4_mc20_e2e.py` errors, all
"`recommendation` field required." Re-running both suites after the peer's edit landed showed
19/19 and 27/27 passing — confirmed as a timing artifact of concurrent shared-worktree
development, not a real regression, before being reported anywhere.

---

## Known, disclosed limitations (not fixed in this pass — out of scope)

- PRAVAAH is still not wired into `CaseWorkflow` — its evidence envelope now propagates correctly
  whenever it *is* invoked, but no case in the current pipeline calls it yet.
- `diffusivity_sensitivity`'s `0.7` threshold is a reasoned reuse of the forcing threshold, not an
  independently-calibrated diffusivity-specific number (disclosed in ADR-0008).
- `particle_loss` on a synthetic-placeholder-seeded run conflates a physical land-blocked fraction
  (~45% asymptote) with an artefact of the placeholder's seed-cloud width — documented previously
  in `docs/science/TRACK_2_FINAL_VALIDATION.md`, unchanged by this pass.
- CHHAYA's `forecast()` stub is unconditionally hardcoded regardless of `current_data` — not
  Track 2's subsystem, not touched beyond the required envelope field.

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

## Final status

**TRACK_2_COMPLETE_AND_FROZEN**

No new Track-2 research direction started. Recommendations for a future, separately-mandated
phase (PRAVAAH→CaseWorkflow wiring, an independently-calibrated diffusivity threshold, a
land-mask-aware particle-loss metric) are documented above, not executed.
