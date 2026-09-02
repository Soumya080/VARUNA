# VARUNA GRID v2 — Canonical Replay: Exact Missing Links

**Task:** STEP 2, POPULATED CANONICAL REPLAY E2E
**Date:** 2026-09-02

Per this task's explicit instruction: if a stage or subsystem turns out not
to be actually wired to `GoldenCaseWorkflow`, record the exact missing link
here rather than silently expanding scope to fix it. Everything below was
found by tracing actual execution (Phase 1), not by reading documentation.

## 0. Load-bearing classification (WORKING / PARTIALLY WORKING / NOT WIRED / BLOCKED / FUTURE)

| Component | Classification | Basis |
|---|---|---|
| `GoldenCaseWorkflow` (lifecycle, idempotency, PRAMAN, `CaseStatus`) | **WORKING** | Proven by 17 passing tests in `tests/e2e/test_canonical_populated_replay.py`; `run_replay_case()` reaches `COMPLETE`, is idempotent, and its `deterministic_run_id` is stable across independent instances |
| `PRATIVARTAN` (origin/Φ reconstruction) | **WORKING** (on this fixture) | `phi_reconstruction` stage `PRODUCED`, `convergence_flag` recorded, section populated on `OperatorCase.origin` |
| `NYAYA` (attribution) | **WORKING** (on this fixture) | `attribution` stage `PRODUCED`, `decision_state=strong_lead`, section populated |
| `PRAVAAH` (forecast) | **WORKING** (on this fixture) | `forecast` stage `PRODUCED`, section populated — see §7 below: not "wired" via a live forecast service call, since this is a replay, but the stage → section path is real and correct |
| `ABHIYAN` (decision/tasking) | **WORKING** (on this fixture) | `decision` stage `PRODUCED`, `n_taskings` present |
| Mission / Alerts | **WORKING** (on this fixture) | Both stages `PRODUCED`; RBAC-enforced mission approval separately proven correct in the STEP 5 authorization work this session also completed |
| `PRAMAN` | **WORKING** | One summary artifact registered per run, content-hashed, `verify()` returns `True` — proven by dedicated test |
| `CHHAYA` | **PARTIALLY WORKING** | The engine itself runs for real (declared-likelihood-ratio, not trained) and is reachable — but only via a separate `CaseIntelligenceService` pass, not through `GoldenCaseWorkflow`/`OperatorCase` directly. See §1. |
| `SMRITI` | **PARTIALLY WORKING** | Same boundary as CHHAYA — genuinely consulted, advisory-only, structured similarity, real retrieval (3/3 synthetic seeded cases matched in the demo) — but only via `CaseIntelligenceService`, not `GoldenCaseWorkflow` itself. See §1. |
| `AgenticLoop` / decision trace / uncertainty assessment | **PARTIALLY WORKING** | Same boundary — real, produces a genuine `proceed_to_decision` terminal action for `CASE-VALID`, but lives entirely in `CaseIntelligenceService`, disconnected from `GoldenCaseWorkflow`'s own call graph and absent from the `OperatorCase` contract |
| `OperatorCase` (the canonical contract) | **WORKING**, with one **NOT WIRED** gap | 9 of 10 declared sections populate correctly from a `GoldenCaseWorkflow` replay run; `engine_mode` now surfaces correctly (this task's fix, ADR-0012); CHHAYA/SMRITI/uncertainty/decision-trace have **no fields on the contract at all** — not degraded, structurally absent |
| Live data orchestration, frontend, benchmark | **FUTURE** | Explicitly out of scope for this task, not evaluated |

Nothing in this table is **BLOCKED** for `CASE-VALID` specifically — every
stage this fixture is capable of exercising did execute and did produce (or
correctly declined to produce) evidence. `CASE-BLOCKED`/`CASE-UNAVAILABLE`/
`CASE-OOD` were exercised as negative controls in the test suite and
correctly reach their respective non-`COMPLETE` terminal states — see the
completion report's stage-by-stage table.

---

## 1. `GoldenCaseWorkflow` never invokes the intelligence layer

**Finding:** `GoldenCaseWorkflow.run_case()` / `.run_replay_case()` /
`._finalize()` contain no reference anywhere to
`varuna_integration.intelligence.CaseIntelligenceService` or
`varuna_agentic.loop.AgenticLoop`. A repo-wide search for
`CaseIntelligenceService(` confirms its only callers are
`scripts/varuna_demo.py` and `tests/integration/test_case_intelligence.py` —
both of which construct it over a `PipelineRun` obtained by calling
`varuna_domain.replay_fixtures.build_replay_run()` **directly**, bypassing
`GoldenCaseWorkflow` entirely.

**Consequence:** CHHAYA (source-hypothesis reasoning), SMRITI (memory
retrieval), the OOD/uncertainty assessment, and the decision trace are all
real and real-ly invoked — but only when a caller separately constructs
`CaseIntelligenceService` and feeds it a `PipelineRun`. Nothing in
`GoldenCaseWorkflow` does this automatically. A case run purely through
`GoldenCaseWorkflow.run_case()`/`run_replay_case()` produces a `CaseResult`
and an `OperatorCase` with **zero** CHHAYA/SMRITI/uncertainty content.

**What this task did, without expanding scope:** the new test
(`tests/e2e/test_canonical_populated_replay.py`) and demo builder
(`scripts/build_canonical_populated_replay_demo.py`) call
`CaseIntelligenceService(smriti=...).run(case_result.run)` — using
`case_result.run`, the SAME `PipelineRun` `GoldenCaseWorkflow` itself already
produced/sourced via `run_replay_case()`. This is a read-only reasoning pass
over an already-canonical result, not a second pipeline execution and not a
bypass: `GoldenCaseWorkflow` is still the only orchestrator constructed, and
its own output is what feeds the intelligence layer. It proves the two
layers CAN compose correctly. It does **not** make `GoldenCaseWorkflow`
itself call the intelligence layer — that would be a real, larger change
(deciding whether every `run_case()`/`run_replay_case()` call should
unconditionally run CHHAYA/SMRITI, what a caller who doesn't want that
overhead should do, and how failures in the intelligence layer should affect
`CaseStatus`) and is out of this task's "smallest safe change" scope.

**Recommendation for a future step:** decide whether `GoldenCaseWorkflow`
should call `CaseIntelligenceService` internally (making its output part of
every `CaseResult`) or whether composing them remains the caller's
responsibility (as this task's test/demo do). Either is defensible; leaving
it undecided-by-default is not.

---

## 2. `OperatorCase` has no fields for CHHAYA/SMRITI/uncertainty/decision-trace

**Finding:** `varuna_contracts.operator_case.OperatorCase` declares:
`system_status`, `observation`, `detection`, `origin`, `ais`, `attribution`,
`validity`, `forecast`, `decision`, `mission`, `alerts`, `recommendation`,
`evidence` (an `EvidenceHealthView` — summary health scores, NOT the
`EvidenceLedger` the intelligence layer builds), `provenance`. There is no
`chhaya`, `hypotheses`, `smriti`, `memory`, `uncertainty`, or `decision_trace`
field anywhere on the contract.

**Consequence:** even if `GoldenCaseWorkflow` were changed to call
`CaseIntelligenceService` internally (see §1), there is currently nowhere on
`OperatorCase` for that output to go. `CaseResult.to_operator_case()` cannot
surface it today no matter what `GoldenCaseWorkflow` internally computes.

**What this task did:** the demo artifact
(`reports/demo/canonical_populated_replay.json`) includes BOTH
`operator_case` (the actual, unmodified `OperatorCase` projection) and a
separate top-level `intelligence` key (the `CaseIntelligence.to_dict()`
output) side by side — proving both are real and populated, without
pretending they are one merged contract. This is not a contract change.

**Recommendation for a future step:** if CHHAYA/SMRITI output should become
part of the canonical operator-facing projection, that is a
`varuna_contracts` schema change requiring its own ADR (per the package's
locked-package convention — see ADR-0006, ADR-0009, ADR-0011, ADR-0012 for
the established pattern), and should be scoped and reviewed on its own, not
folded into a replay-proof task.

---

## 3. `manifest_artifact_id` is never populated on the `GoldenCaseWorkflow` path

**Finding:** `GoldenCaseWorkflow._finalize()` registers exactly one PRAMAN
artifact per run — `artifact_type="golden_case_run"`, a small summary dict
(`run_id`, `terminal_status`, `blocked_at`, `evidence_mode`). It does not
construct or register a full `EvidenceManifest`. `ProvenanceView.manifest_artifact_id`
(on `OperatorCase.provenance`) is therefore always `None` for a
`GoldenCaseWorkflow`-produced case; `artifact_ids` (a list) IS correctly
populated with the one summary artifact's ID.

**Consequence:** a consumer of `OperatorCase.provenance` cannot resolve a
single "the manifest for this case" artifact; they can only see the one
summary artifact ID. This is a narrower gap than §1/§2 — the PRAMAN record
exists and verifies (see the completion report's Phase 10 section) — it is
simply not a *manifest*-shaped artifact.

**What this task did:** documented it, and adjusted the new test/demo to
assert what is actually true (`artifact_ids` is non-empty) rather than assert
`manifest_artifact_id is not None`, which would be false for every
`GoldenCaseWorkflow`-produced case today, replay or otherwise.

**Recommendation for a future step:** decide whether `GoldenCaseWorkflow`
should also register a full manifest (mirroring whatever pattern the legacy
`CaseWorkflow`/`PramanService` path may or may not already establish
elsewhere) — not attempted here, since it touches PRAMAN's registration
contract and this task's scope is proving the replay path, not extending
PRAMAN.

---

## 4. What IS fully wired (stated for balance, not just gaps)

- `forcing`, `ais_ingest`, `netra_detection`, `phi_reconstruction`,
  `attribution`, `validity`, `forecast`, `decision`, `mission`, `alerts` —
  all ten `RealE2EPipeline`-shaped stages are produced by `CASE-VALID` and
  correctly projected onto `OperatorCase` sections.
- PRAMAN's single summary artifact is genuinely content-hashed and
  genuinely verifies (`PramanService.verify()` returns `True`).
- `engine_mode` (REAL/REPLAY/SIMULATED) is now surfaced on
  `OperatorCase.system_status` (ADR-0012, this task) — previously computed
  and silently dropped.
- Idempotency (`run_replay_case()` called twice returns the same
  `deterministic_run_id`, `idempotent_replay=True` on the second call) works
  correctly end-to-end, verified by this task's new tests.
