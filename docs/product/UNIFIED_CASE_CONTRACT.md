# VARUNA GRID v2 — Unified Case Contract

**Task:** STEP 3, Unified Product Case Contract
**Date:** 2026-09-02
**Contract:** `varuna_contracts.operator_case.OperatorCase` (schema `v1`, unchanged version — see ADR-0013)
**Composition:** `varuna_integration.product_case.build_product_case()`

## What a product caller gets

```python
from varuna_integration.product_case import build_product_case

result = workflow.run_replay_case(case_id, "CASE-VALID")   # or run_case()
case = build_product_case(result, workflow, smriti=smriti_store)
```

`case` is a normal `OperatorCase` — every field that existed before STEP 3
means exactly what it always meant. One field is new.

## Field map

### CORE CASE
| Field | Type | Source |
|---|---|---|
| `case_id` | `str` | `Case.case_id` |
| `system_status.case_status` | `str` | `CaseStatus` |
| `system_status.engine_mode` | `str \| None` | `ReproducibilityRecord.engine_mode` (ADR-0012) — `"real"` / `"replay"` / `"simulated"` / `None` (legacy `CaseWorkflow` path) |
| `system_status.scientific_status` | `str` | `ScientificStatus` |
| provenance / run identity | `provenance.*` | `ReproducibilityRecord` via `_provenance()` |

`run_id` is not a top-level `OperatorCase` field; it lives on
`ReproducibilityRecord` (`result.reproducibility.run_id`) alongside
`deterministic_run_id`, both outside this contract by design — they are
per-execution identifiers, not case state, and are already exposed via
`CaseResult` directly.

### SCIENTIFIC
| Field | Type | Populated by |
|---|---|---|
| `detection` | `SectionEnvelope[SlickDetection]` | NETRA |
| `origin` | `SectionEnvelope[PhiField]` | PRATIVARTAN |
| `ais` | `SectionEnvelope[list[AISCandidateView]]` | AIS ingest |
| `attribution` | `SectionEnvelope[AttributionResultV2]` | NYAYA |
| `validity` | `SectionEnvelope[ValidityGateResult]` | Validity Gate |
| `forecast` | `SectionEnvelope[ForwardForecast]` | PRAVAAH |
| `decision` | `SectionEnvelope[list[AssetTasking]]` | ABHIYAN |
| `recommendation` | `OperationalDecisionState` | derived from `validity` (never a second gate) |
| `mission` | `SectionEnvelope[list[MissionRecord]]` | Mission FSM |
| `alerts` | `SectionEnvelope[list[AlertView]]` | Alert service |

Unchanged since before STEP 3 — none of these sections were touched by this
task.

### INTELLIGENCE (new — `OperatorCase.intelligence: IntelligenceSection`)
| Field | Type | Populated by |
|---|---|---|
| `intelligence.status` | `ProducerStatus` | `PRODUCED` when composed against a real `PipelineRun`; `NOT_YET_PRODUCED` (with `.reason`) otherwise |
| `intelligence.uncertainty` | `UncertaintyAssessment \| None` | `CaseIntelligenceService`'s `UncertaintyAssessor` |
| `intelligence.hypotheses` | `SourceHypothesisEnvelope \| None` | CHHAYA (`SourceHypothesisEngine`) |
| `intelligence.memory_hits` | `list[dict]` | SMRITI (`SmritiStore.retrieve_similar_cases`) — advisory-only, per `varuna_smriti`'s own contract |
| `intelligence.decision_trace` | `DecisionTrace \| None` | `AgenticLoop` |
| `intelligence.next_best_action` | `NextBestAction \| None` | the last step's action in `decision_trace`, if any |
| `intelligence.evidence_lineage` | `list[dict]` | `EvidenceLedger.audit_trail()` |

### AUDIT
| Field | Type | Source |
|---|---|---|
| `provenance.artifact_ids` | `list[str]` | PRAMAN (`golden_case_run` summary artifact) |
| `provenance.model_versions` | `dict[str, str]` | per-stage `detail.model_version` |
| `provenance.manifest_artifact_id` | `str \| None` | **always `None` today** — `GoldenCaseWorkflow` registers one summary artifact, not a full `EvidenceManifest` (named gap, `docs/product/CANONICAL_REPLAY_GAPS.md` §3) |
| `intelligence.evidence_lineage` | `list[dict]` | full evidence audit trail, see above |

## Explicit states, not fabricated ones

Per Task 3/4's requirement, every section uses the SAME vocabulary that
already existed, never a new "looks complete" shortcut:

- `ProducerStatus.NOT_YET_PRODUCED` — the stage/service hasn't run for this
  case, or (for `intelligence`) wasn't composed. Always carries `.reason`.
- `ProducerStatus.BLOCKED` — a precondition stopped it; `.reason` names it.
- **EMPTY-BUT-VALID is not a separate enum value** — it is
  `PRODUCED` with an empty collection (e.g. `intelligence.memory_hits == []`
  when SMRITI genuinely found nothing, or `ais.status == NOT_YET_PRODUCED`
  when the AIS *stage* ran but returned zero tracks — see STEP 2's
  completion report for why that specific case is `NOT_YET_PRODUCED`, not
  `PRODUCED` with an empty list: zero AIS evidence is not the same fact as
  "AIS section exists but is trivially empty," and the existing
  `_ais_section()` logic already encodes that correctly).

## Real / Replay / Simulated

`engine_mode` and every section's `evidence_mode` remain fully independent,
per ADR-0012 and re-verified by this task's own tests
(`test_evidence_mode_and_engine_mode_preserved_through_composition`,
`test_simulated_fixture_never_upgraded_by_composition`). Composition adds a
third independent axis — `intelligence.hypotheses.envelope.mode` — which is
likewise never silently promoted; verified directly against `CASE-SIMULATED`.

## What is NOT in this contract, and why

- No frontend-oriented derived fields (e.g., no pre-formatted display
  strings, no aggregated "everything is fine" flag). The contract stays a
  re-shaping of what backend producers already computed, per its own module
  docstring — composition did not change that principle.
- No mutation path from `intelligence` back into `case`, `run`, or PRAMAN.
  `build_product_case()` is read-only by construction (`model_copy`, never
  in-place assignment) — see ADR-0013 and the dedicated mutation test.

## How to get one today

Only `GoldenCaseWorkflow`-produced cases can have `intelligence.status ==
PRODUCED`. The live `GET /v1/cases/{case_id}/operator-view` endpoint is
still backed by the legacy `CaseWorkflow` (STEP 1's documented, deliberate
non-migration), so every response from it today reports
`intelligence.status == NOT_YET_PRODUCED` honestly. To get a fully composed
unified case today, call `build_product_case()` directly against a
`GoldenCaseWorkflow.run_case()`/`.run_replay_case()` result — exactly as
`tests/integration/test_product_case_composition.py` does.
