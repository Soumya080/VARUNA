# VARUNA GRID v2 — Post-Integration Research Questions

**Session:** VARUNA_PRODUCT_READY hardening
**Date:** 2026-09-02

What the running product revealed this session, for the next
Intelligence/Research session to pick up. No long experiments were run to
produce this list — these are observations from integration work and two
targeted, no-training diagnostics.

## 1. NETRA / detection

- **The class-probability heuristic and the energy-score signal disagree on
  MC20.** `max_probability` says out-of-domain (5 orders of magnitude below
  threshold); the energy score says the representation is unremarkable (p50-p75
  of the in-domain reference). `varuna_integration.ood_energy.combine_ood_signals()`
  now reports this as BORDERLINE rather than picking one, but the underlying
  question — is NETRA confidently, correctly negative on MC20, or is it
  out-of-domain in a way the energy score doesn't capture — is unresolved and
  is a real research question, not an engineering one.
- **The documented VV/VH channel-binding fix (`resolve_frozen_v0_2_channel_binding`)
  has zero callers.** `scripts/build_mc20_event_gold.py` does not apply it.
  A non-destructive diagnostic this session showed applying it does not change
  MC20's conclusion (both orderings ~1e-6, still ~5 orders below threshold),
  but the fix should still be wired into the Gold-build script for scientific
  correctness on any *future* scene — MC20 happened not to be sensitive to it,
  which is not evidence that no scene ever will be.
- **`NetraModelSpec` has no `preprocessing_version` field.** Nothing mechanically
  prevents a future checkpoint/preprocessing mismatch from running silently.
  `golden_case_engine.detector_provider_info()`'s `ASSUMED_NETRA_PREPROCESSING_VERSION`
  constant is a convenience note, not enforcement.
- The energy-score reference (`reports/netra_v02/ood_energy_reference_v0_1.json`)
  was built from 200 of 3,616 val tiles for tractability. A full-split
  reference, and a genuine held-out OOD corpus to measure false-positive/
  false-negative rates against, would move this from "reference comparison"
  toward "calibrated" — which it explicitly is not yet.

## 2. CHHAYA

- `distance_to_shore_km` still cannot be wired to any real CHHAYA case: the
  only available adapter (`varuna_source_adapters/static_gis.py`) returns a
  hardcoded `10.0` for every query. Wiring it would fabricate identical
  coastal-proximity support for every case (10.0 km sits inside the
  `COASTAL_PROXIMITY_KM = 15.0` boundary). A real GIS coastline lookup is a
  research/data-engineering item, not something this session should
  approximate.
- CHHAYA's priors (`BASE_PRIORS`, `GULF_OF_MEXICO_PRIORS`) and likelihood-ratio
  magnitudes (`_STRONG/_MODERATE/_WEAK`) remain declared, not fit from data.
  Demo B's hypothesis distribution shifted materially (natural_seep
  0.668→0.738) purely from wiring previously-discarded real inputs (corridor
  count, wind, area, elongation, phi convergence) into an unchanged engine —
  worth stress-testing whether the declared likelihood ratios are sane across
  a wider input range than the two demo cases exercise.

## 3. Agentic loop / uncertainty

- The fail-closed guard (STOP_INSUFFICIENT_EVIDENCE when data-quality or OOD
  assessment is missing) was validated by this session's own earlier test
  suite, not new work here. Worth extending: what happens when the energy
  score and class-probability heuristic disagree in the OTHER direction
  (probability says in-domain, energy says out-of-domain)? No fixture
  exercises that combination yet.

## 4. Evidence / observability

- `packages/varuna_infra/observability.py` had zero callers anywhere in the
  repository before this session — not a stub filling a used interface, but
  genuinely dead code. The real version built this session
  (`build_case_timeline`, `summarize_case_state`, a working `MetricsTracker`)
  is also not yet called from `apps/api` — it is available, tested, and ready
  to wire into an operator-facing endpoint, but that wiring is Phase 9/10
  work, not done here.
- `MetricsTracker` is process-local, in-memory, and not connected to any
  external metrics backend (Prometheus, etc.). That is a deployment-time
  decision, deliberately not made here.

## 5. Canonical architecture

- **The live HTTP API does not use `GoldenCaseWorkflow`.** Every case-facing
  route in `apps/api/routers/cases.py` is built on `varuna_domain.CaseWorkflow`,
  whose `reconstruct()` runs synthetic forcing under a SIMULATED envelope.
  This session flagged it prominently in `case_workflow.py`'s own docstring
  and in `docs/product/VARUNA_PRODUCT_CURRENT_STATE.md` rather than migrating
  it, because `apps/api/operator_case_view.py` (459 lines) is tightly coupled
  to `CaseWorkflow` and was active peer territory. The migration path is
  named (repoint `get_workflow()` at `GoldenCaseWorkflow`, reconcile
  `operator_case_view.py` against `CaseResult`), but not attempted.

## 6. Scope not reached this session

Phases 8 (live data orchestration layer), 9 (full API contract), 10 (frontend
productization), 12 (benchmark), most of 13 (E2E matrix beyond what already
existed), 14 (UX polish) were not built this session — see
`reports/product/varuna_product_status.json` for the itemized BUILT/VERIFIED/
PARTIALLY BUILT/BLOCKED/FUTURE breakdown. These are not "discovered problems"
in the sense the other sections are; they are named scope this session did
not reach, and are the most direct input to what the next session should
prioritize.
