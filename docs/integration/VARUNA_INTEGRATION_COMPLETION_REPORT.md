# VARUNA GRID v2 — Integration Completion Report

**Date:** 1 Sep 2026 · **Session type:** product build / integration
**Branch:** `feat/netra-real-training`

**Frozen-asset safety:** no training was started or resumed; no checkpoint,
Gold dataset, MC20 corpus, or official evaluation artifact was modified. NETRA
v0.3-B1 was found already **complete** (30 epochs, `done in 59225.8s`) with no
training process running; it remains a FROZEN, NOT-DEPLOYED failed research
baseline. NETRA v0.2 remains the deployed MVP detector and was used read-only.

---

## 1. Architecture implemented

```
DATA INGESTION ──► DATA GUARD ──► NETRA v0.2 ──► DETECTION EVIDENCE ──► EVIDENCE LEDGER
                                                                              │
   ┌──────────────────────────────────────────────────────────────────────────┘
   ▼
PRATIVARTAN/Φ ──► AIS ──► CHHAYA ──► NYAYA ──► OOD/UNCERTAINTY ──► NEXT-BEST-ACTION
                                                                        │
   ┌────────────────────────────────────────────────────────────────────┘
   ▼
VALIDITY GATE ──► PRAVAAH ──► ABHIYAN ──► RBAC ──► MISSION ──► ALERTS ──► PRAMAN ──► SMRITI
                                                                              │
                                                          CASE ENGINE / REPLAY ──► OPERATOR CONTRACT
```

The chain is executable end to end. Two demonstrations prove it
(`scripts/varuna_demo.py`), one on real MC20 data and one on a populated replay
case.

## 2. Modules completed this session

| Module | Location | What it is |
|---|---|---|
| Detection evidence contracts | `varuna_contracts/detection_evidence.py` | `DetectionEvidenceEnvelope`, `Measured`, `MeasurementStatus`, `OODRisk`, `UncertaintyAssessment` |
| Source-hypothesis contracts | `varuna_contracts/source_hypothesis.py` | `SourceHypothesisEnvelope`, `SourceClass`, `HypothesisMethod` |
| Action contracts | `varuna_contracts/action.py` | `NextBestAction`, `ActionRecord`, `DecisionTrace` |
| **Evidence Ledger** | `varuna_evidence/ledger.py` | append / revise-with-lineage / retract / contradiction / audit trail |
| **CHHAYA v0.1** | `varuna_chhaya/hypothesis_engine.py` | declared-likelihood-ratio Bayesian source-hypothesis engine |
| **SMRITI v0.1** | `varuna_smriti/memory.py` | persistent case memory + structured (non-embedding) similarity retrieval |
| **Agentic loop** | `varuna_agentic/loop.py` | `UncertaintyAssessor`, `ActionSelector`, `AgenticLoop` |
| **Authorization** | `varuna_infra/authorization.py` | `Principal`, `authorize()`, `AuditLog`, `AuthorizationError` |
| Case intelligence | `varuna_integration/intelligence.py` | bridges `PipelineRun` into the evidence/reasoning stack |
| Demos | `scripts/varuna_demo.py` | Demo A (real MC20), Demo B (populated replay) |

## 3. Modules reused unchanged

`GoldenCaseWorkflow` (canonical case engine), `RealE2EPipeline` stage
orchestration, PRATIVARTAN, NYAYA, the Validity Gate, PRAVAAH, ABHIYAN, the
mission FSM, alert severity/dedupe/materiality/routing, `EvidenceEnvelope`,
`EvidenceMode`, and every repository. **No second pipeline was created.** The
intelligence layer consumes what the canonical pipeline produced; it runs no
advection, attribution, or gate logic of its own, and a test asserts that every
evidence item it records comes from a pipeline stage or one of four named
non-pipeline producers.

## 4. Modules modified (and why)

| File | Change |
|---|---|
| `varuna_missions/service.py` | `approve_and_assign()` now requires a `Principal` and authorizes before mutating |
| `varuna_missions/protocol.py` | signature updated to match |
| `apps/api/routers/missions.py` | added `POST /v1/missions/{id}/approve` (previously no HTTP path reached approval at all) |
| `varuna_praman/praman.py` | dict artifacts are now content-hashed; added `verify()` |
| `varuna_integration/netra_boundary.py` | peak activation now recorded on the no-detection path |
| `varuna_domain/replay_fixtures.py` | `CASE-VALID` given activation statistics |
| `varuna_integration/pipeline.py` | unchanged this session (PRAVAAH work landed previously) |

## 5. New contracts

See **ADR-0010** for the full rationale. The load-bearing idea is `Measured`:
every fabricable quantity carries a `MeasurementStatus`, and two validators make
dishonesty unrepresentable — `UNAVAILABLE` with a value is rejected, and any
other status with `value=None` is rejected.

## 6. CHHAYA design

A deterministic Bayesian update over **declared** likelihood ratios. Every
weight is a hand-written constant with a stated justification; nothing is
learned, fitted, or calibrated. `HypothesisMethod.DECLARED_LIKELIHOOD_RATIO`
and a `methodology_note` containing "NOT a trained or learned model" and
"UNCALIBRATED" are stamped on every envelope, and a test asserts both strings
are present. Hypothesis classes: vessel-associated, coastal, natural seep,
other anthropogenic, unknown.

Two honesty properties worth naming:

- **Absent evidence contributes nothing.** A factor whose input was not
  supplied adds no likelihood ratio at all. This was enforced only after a test
  caught the opposite: `n_ais_tracks` defaulted to `0`, so "AIS was never
  consulted" was indistinguishable from "AIS was consulted and found nothing",
  and a *parameter default* was silently acting as evidence. The parameter is
  now `int | None`.
- **Spatial proximity is weaker than a temporal match**, mirroring the AIS
  join's own rule that spatial candidacy is never promoted into temporal
  evidence.

A future learned CHHAYA can replace the engine behind the same envelope
without touching a caller.

## 7. SMRITI design

Persistent JSON-lines case memory with structured similarity over six weighted
components (geography, environment, morphology, source hypothesis, attribution
pattern, seasonal proximity). Deliberately **not** text embeddings: "cases 40 km
apart in the same wind regime" is a more meaningful neighbour relation here than
prose similarity, and the structured metric is inspectable —
`similarity_breakdown.components` shows exactly what drove a match.

Guards: a `min_coverage` floor rejects matches assessed on too little shared
data (two near-empty records otherwise "match" trivially on their one shared
field); missing components are reported in `unavailable` rather than scored as
zero; and a corrupt line in the store is skipped rather than taking down the
whole memory.

**Memory is advisory, never authoritative.** Every retrieval carries
`advisory_only=True` and a note stating it must never override current
evidence. This is asserted in tests. SMRITI does **not** learn — nothing here
updates a model, prior, or threshold.

## 8. Agentic loop design

`OBSERVE → ASSESS → IDENTIFY UNCERTAINTY → SELECT ACTION → EXECUTE → UPDATE
EVIDENCE → REASSESS → ACT or STOP`, as a deterministic priority-ordered rule
set. **No LLM is involved**; the module contains no model call. Every action
records the named uncertainty that motivated it, and `DecisionTrace.render()`
answers "why is this case in this state?" without reading source.

Safety posture encoded in the ordering: establish whether the perception input
is trustworthy *before* reasoning on top of it, and resolve contradictions
before proceeding.

**The fail-closed guard is the most important part of this module**, and it was
added in response to a bug found by its own test: the loop originally reached
`PROCEED_TO_DECISION` whenever every action had been *attempted*, which meant a
case whose executor failed on every call still advanced to a decision on
evidence that was never gathered. The selector now checks that the evidence
actually exists, not that the attempt was made.

## 9. Evidence flow

`PipelineRun` → `ledger_from_run()` → Evidence Ledger → `UncertaintyAssessor`
→ `ActionSelector` → executors (CHHAYA, SMRITI, OOD, data-guard) → updated
ledger → `CaseIntelligence` → PRAMAN artifact (content-hashed, verifiable).

Only stages that actually **produced** something become evidence. A stage that
reported `NOT_YET_PRODUCED`/`BLOCKED` is deliberately not recorded, because an
item count that includes "nothing happened" would imply the case is better
supported than it is; the stage's reason remains on the pipeline run.

## 10. Real / replay / simulated behaviour

`EvidenceMode` propagates unchanged from each pipeline stage into the ledger,
and `EvidenceLedger.worst_mode()` applies the same monotonic-worsening rule as
`EvidenceEnvelope`. An empty case returns `None`, not `REAL` — defaulting to
REAL would be a lie. Tests assert a SIMULATED case never reports REAL anywhere
in the chain.

## 11. API integrations

Not built this session. Sentinel-1/AIS/ERA5/CMEMS adapters already exist and are
already exercised on real MC20 data; no live-fetch scheduler, retry, or caching
layer was added. Recorded as a remaining gap rather than stubbed.

## 12. Tests executed

| Suite | Result |
|---|---|
| Full regression (`unit`+`contract`+`integration`+`e2e`) | **674 passed, 10 skipped, 1 failed** (283s) |
| New: `test_evidence_ledger.py` | 13 passed |
| New: `test_chhaya_hypothesis_engine.py` | 15 passed |
| New: `test_smriti_memory.py` | 18 passed |
| New: `test_agentic_loop.py` | 15 passed |
| New: `test_authorization_enforcement.py` | 13 passed |
| New: `test_case_intelligence.py` | 17 passed |

The single failure is `tests/unit/test_netra_training.py::test_netra_training_loop`
(`TypeError: 'NetraSample' object is not subscriptable`) — NETRA-owned, pre-existing,
identical to every prior audit this week, untouched here.

## 13. E2E results

**DEMO A — real MC20.** Real ERA5/CMEMS forcing, real AIS, the real frozen v0.2
checkpoint over 9 real SAR tiles. NETRA returns **no detection**, peak activation
**3.07e-06** against a 0.806 threshold. The OOD assessor classifies this
`OUT_OF_DOMAIN`, the detection evidence carries the limitation "confidence must
not be treated as a calibrated probability", and the agentic loop terminates
`STOP_INSUFFICIENT_EVIDENCE`. **No spill was declared and no detection was
fabricated.** This is the demo's actual value: correct, traceable handling of a
hard real case.

**DEMO B — populated replay.** Full chain: evidence ledger populated across
forcing/AIS/origin/attribution/validity/forecast/decision, OOD `in_domain`,
CHHAYA ranking source hypotheses, SMRITI retrieving prior cases (advisory),
agentic loop reaching `PROCEED_TO_DECISION`, RBAC correctly **denying** an
analyst and **denying** the system principal while **allowing** a duty officer,
and a content-hashed PRAMAN artifact that verifies.

## 14. Failure handling

Everything fails closed and says why. Proven by test: executor exceptions are
recorded not propagated; a case with no detection stops rather than reasoning on
nothing; an OOD detection never reaches a decision; contradictions are addressed
before any decision; budget exhaustion is reported as insufficient, never as
success; a denied authorization leaves the mission untouched; a corrupt memory
line does not destroy the store.

## 15. Frontend contract

Not modified — externally owned, per instruction. The backend surface the
frontend needs is stable: `GET /v1/cases/{case_id}/operator-view` (8 sections),
plus `CaseIntelligence.to_dict()` which serialises evidence ledger, uncertainty,
detection evidence, hypotheses, memory hits, audit trail, and rendered decision
trace as JSON.

## 16. Remaining gaps

- **Live API fetch path** (scheduler/retry/caching for Sentinel-1/AIS/ERA5/CMEMS) not built.
- **Frontend** is still a Vite scaffold; no UI consumes the new contracts yet.
- **Observability** remains a 13-line stub; the decision trace partly compensates.
- **RBAC on other endpoints** — only mission approval is enforced. The approve
  endpoint authenticates via `X-User-Id`/`X-User-Role` headers, which is an
  interim mechanism; signed JWTs already exist in `varuna_infra.auth` and should
  replace it before any untrusted-network deployment.
- **CHHAYA is uncalibrated**, and `distance_to_shore_km` / `wind_speed_ms` are
  not yet wired from real data into the engine's inputs.
- **Preprocessing compatibility is still unverified** between checkpoint and
  input pipeline (pre-existing; see `CASE_ORCHESTRATION_RECONCILIATION.md` §8).
- `CaseWorkflow` (the older synthetic-forcing path) still exists alongside
  `GoldenCaseWorkflow`; the reconciliation is documented but not enforced.

## 17. Scientific limitations

- NETRA v0.2 does **not** work on MC20. Its null there is a real result with an
  unresolved cause (`MIXED_CAUSE`, representation-dominant).
- The OOD classifier is a **heuristic over reported activations**, not a
  calibrated OOD detector. Every rationale string says so.
- CHHAYA's posteriors are internally consistent but **uncalibrated** — relative
  plausibility under declared assumptions, not empirical frequencies.
- SMRITI similarity weights are declared, not fitted.
- Demo B is REPLAY at the **run** level, but the `CASE-VALID` fixture stamps
  `EvidenceMode.REAL` on its **stages** (it represents a recording of what a real
  validated run produces), so `worst_mode` reports `real`. This is the fixture's
  deliberate design, not a provenance upgrade — but it does mean "Demo B is
  simulated throughout" would be an inaccurate summary. The genuinely
  simulated-labelled path is the `CASE-SIMULATED` fixture, covered by tests.
- Seeded SMRITI history in the demos is explicitly synthetic
  (`provenance_source="SYNTHETIC-DEMO-SEED (not a real historical case)"`).

## 18. Next research backlog (NOT started here)

B1 MIL/top-k ablation · stronger-label acquisition · domain adaptation ·
low-wind dataset expansion · uncertainty/OOD improvement (replacing the
heuristic with a calibrated detector) · CHHAYA calibration against outcome data
once a labelled corpus exists.

---

## Bugs found and fixed during this session

Listed because each was found by a test written against the new code, and each
was a real defect rather than a test artifact:

1. **Agentic loop fail-open** — reached `PROCEED_TO_DECISION` when all actions
   had been attempted but none had succeeded.
2. **CHHAYA parameter default acting as evidence** — `n_ais_tracks=0` made an
   unsupplied argument indistinguishable from a measurement.
3. **CHHAYA factor miscount** — counted contributions rather than distinct
   signals, so one input looked like two.
4. **`hypothesis.py` module shadowing** — the new contracts module shadowed the
   installed `hypothesis` test library and broke collection for the *entire*
   suite (7 errors + INTERNALERROR). Renamed to `source_hypothesis.py`.
5. **`EvidenceLedger.latest()` tie-break** — `max(key=recorded_at)` returned the
   *earlier* item when two shared a timestamp, so "latest" could be stale.
6. **OOD reported inconsistently** — `DetectionEvidenceEnvelope` said
   `out_of_domain` while `UncertaintyAssessment` said `unknown` for the same case.
7. **PRAMAN never hashed dicts** — and `CaseWorkflow` registers only dicts, so in
   practice *no* artifact had ever been content-hashed.
8. **NETRA peak activation discarded** on the no-detection path, making "nearly
   fired" indistinguishable from "no representation for this input".
