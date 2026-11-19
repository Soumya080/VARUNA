# VARUNA GRID v2 — Current State (pre-integration audit)

**Date:** 1 Sep 2026 · **Method:** direct source/test/process inspection, not prior-report trust.

## Frozen assets — verified present, untouched by this session

| Asset | State |
|---|---|
| NETRA v0.2 checkpoint (`9f38c690…`) | Frozen. Current MVP detector, DEPLOYED. |
| NETRA v0.3-B1 (`pilot_01_run2/last.pt`) | **Training COMPLETE** (30 epochs, "done in 59225.8s"); no process running. FAILED RESEARCH BASELINE, FROZEN, NOT DEPLOYED. |
| MC20 Gold, NETRA Gold, CALM-GRD-HOLDOUT, Zenodo Part III | Untouched. |

No training was started or resumed. GPU idle at audit time (19%, 1.3 GB — B1 had already finished).

## Implemented and working (reuse unchanged)

| Component | Location | Evidence |
|---|---|---|
| Case Engine (canonical) | `varuna_domain/golden_case_engine.py` | `GoldenCaseWorkflow`, idempotency, `deterministic_run_id`, replay |
| Real pipeline stages | `varuna_integration/pipeline.py` | 10 stages, real ERA5/CMEMS/AIS, fail-closed |
| PRATIVARTAN / Φ | `varuna_prativartan/` | real ensemble, ADR-0007 sensitivity |
| NYAYA | `varuna_nyaya/services.py` | real Bayesian attribution |
| Validity Gate | `varuna_nyaya/validity_gate.py` | 11 checks, reason codes, fail-closed |
| PRAVAAH | `varuna_pravaah/cube_provider.py` + `pipeline._forecast()` | integrated + verified (prior session) |
| ABHIYAN | `varuna_abhiyan/service.py` | 5-state gate matrix |
| Mission FSM | `varuna_missions/` | two-step approval, contract-level gate |
| Alerts | `varuna_alerts/` | severity/dedupe/materiality/role-routing |
| OperatorCase | `apps/api/operator_case_view.py` | 8 sections, provenance rollup |
| EvidenceMode / envelopes | `varuna_contracts/evidence.py` | monotonic worsening, ADR-0006 |

## Missing entirely (0 references found repo-wide)

`DetectionEvidenceEnvelope` · `EvidenceLedger` · `NextBestAction` · `UncertaintyAssessment` · `SourceHypothesisEnvelope`

## Partial / stubbed

| Component | Actual state |
|---|---|
| **CHHAYA** | `MockChhayaProvider` is a real AIS-coverage heuristic, but `ChhayaInferenceService.investigate()` returns `{}` with a signature that does not match its own ABC, and defines a `forecast()` belonging to a different protocol. **No canonical case path calls CHHAYA at all.** |
| **SMRITI** | Protocol + mock only (116 lines total). No persistence, no structured retrieval, no similarity. |
| **Data Guard** | `varuna_data_guard/guard.py` (69 lines) validates slick points / track count / obs-time only. Not an ingestion-boundary guard: no schema, channel-ordering, dimension, or provenance validation. |
| **PRAMAN** | Registers artifacts but only hashes `bytes`; dict payloads are never hashed and never reach the object store. |
| **RBAC** | `has_permission()` fully implemented and unit-tested, **zero production call sites**. Missions router is GET-only; `approve_and_assign()` unreachable over HTTP and unauthorized. |
| **Observability** | 13-line no-op module. |

## Broken contracts found

1. `ChhayaInferenceService.investigate()` — signature mismatch vs `ChhayaProvider` ABC, returns `{}`.
2. `has_permission()` — enforcement boundary absent (security-relevant).
3. PRAMAN dict artifacts — never content-hashed, so `EvidenceManifest` integrity is unverifiable for the payloads actually used.

## Recommended implementation order (followed by this session)

1. `DetectionEvidenceEnvelope` + `UncertaintyAssessment` contracts
2. Evidence Ledger
3. Data Guard extension (ingestion boundary, fail-closed)
4. CHHAYA v0.1 (explicit rule/Bayesian engine, honestly labelled)
5. SMRITI v0.1 (persistent, structured similarity retrieval)
6. `NextBestAction` + agentic orchestration loop
7. RBAC enforcement at authorization boundaries
8. PRAMAN completion
9. Wire into Case Engine; demos; tests; docs

**Rule applied throughout:** prefer incremental integration; do not rewrite working modules; do not duplicate responsibilities; no second case engine.
