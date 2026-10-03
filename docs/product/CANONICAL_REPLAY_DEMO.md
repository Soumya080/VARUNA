# VARUNA GRID v2 — Canonical Populated Replay Demo

**Task:** STEP 2, POPULATED CANONICAL REPLAY E2E
**Date:** 2026-09-02
**Artifact:** `reports/demo/canonical_populated_replay.json`
**Builder:** `scripts/build_canonical_populated_replay_demo.py`

## What this replay represents

One case, `CASE-VALID-CANONICAL-REPLAY-DEMO`, executed **exclusively**
through `GoldenCaseWorkflow.run_replay_case()` — no `RealE2EPipeline(...)`
and no `CaseWorkflow(...)` are constructed anywhere in the builder script.
The fixture sourced is `CASE-VALID` (`packages/varuna_domain/replay_fixtures.py`),
a hand-built `PipelineRun` that models what a case looks like when a frozen,
calibrated NETRA checkpoint fires cleanly on a clear scene with a
well-behaved forcing field: every one of the ten pipeline stages reaches
`PRODUCED`.

## What is real / replayed / simulated

Two independent facts, both surfaced, never collapsed into one:

- **`engine_mode: "replay"`** — how this run was *executed*. It did not run
  live inference, real forcing, or a real Bayesian attribution; it sourced a
  canned, deterministic `PipelineRun` object. This is now visible on
  `OperatorCase.system_status.engine_mode` (ADR-0012, added by this task —
  it previously existed only on `ReproducibilityRecord` and never reached
  the contract a consumer actually reads).
- **`evidence_mode: "real"`** on every section — what the evidence *claims
  to model*. `CASE-VALID`'s own source comments call every number "SYNTHETIC
  like every other number in this file"; the REAL label means "this is what
  real, successful evidence would look like," not "this was observed live."

A viewer of this demo who reads only `engine_mode` learns it was replayed. A
viewer who reads only a section's `evidence_mode` learns what kind of
evidence that section models. Reading either one alone and concluding the
other is exactly the mistake this task's Phase 7 instruction warns against
("do not convert replay to REAL just because it contains recorded real-world
values") — the fix here was making the REPLAY fact visible at all, not
changing the REAL label, which was already honest about what it models.

## Which stages actually produced evidence

Nine of ten sections: `detection`, `origin` (PRATIVARTAN/Φ), `attribution`
(NYAYA), `validity`, `forecast` (PRAVAAH), `decision` (ABHIYAN), `mission`,
`alerts`, `observation`. All `PRODUCED`.

**`ais` is the deliberate exception** — `NOT_YET_PRODUCED`, and this is
correct, not a defect. The `ais_ingest` *stage* executed successfully
(`StageStatus.PRODUCED`) and reported `n_returned=0`: zero vessel tracks
nearby, which is a genuine, valid outcome, not a failure. Zero tracks means
zero AIS *evidence*, so the evidence section honestly reports
`NOT_YET_PRODUCED` with reason `"No AIS tracks were ingested for this
case."`. This is the "stage executed" vs. "stage produced evidence"
distinction this task's Phase 4 explicitly requires preserving, and it is
preserved: nothing was changed to make AIS look populated.

Beyond the `OperatorCase` contract, a **separate, read-only reasoning pass**
(`CaseIntelligenceService.run(result.run)`, run over the exact same
`PipelineRun` `GoldenCaseWorkflow` produced — not a second execution)
produces:

- **CHHAYA** — a real hypothesis run (`DECLARED_LIKELIHOOD_RATIO` method,
  not a trained model), top class `natural_seep`.
- **SMRITI** — genuinely consulted (advisory-only, three synthetic seeded
  historical cases available for retrieval).
- **Uncertainty/OOD** — `ood_risk: in_domain` for this fixture's activation
  statistics.
- **Decision trace** — terminal action `proceed_to_decision`.

This intelligence output is real and genuinely produced, but is **not**
currently part of the `OperatorCase` contract or of `GoldenCaseWorkflow`'s
own internal call graph — see `docs/product/CANONICAL_REPLAY_GAPS.md` §1–2
for the exact, undecided-by-this-task architectural question that leaves
open.

## What remains unavailable

- `ais` section — `NOT_YET_PRODUCED` (see above; correct, not a gap).
- `provenance.manifest_artifact_id` — always `None` on the
  `GoldenCaseWorkflow` path (it registers one summary artifact, not a full
  manifest). `provenance.artifact_ids` correctly lists that one artifact.
  See gaps doc §3.

## Why this is a valid product demonstration

1. **It proves the claim STEP 2 exists to prove**: `GoldenCaseWorkflow` is a
   usable canonical execution surface that produces a genuinely populated
   `OperatorCase` — nine of ten sections `PRODUCED`, with correct, verified
   provenance and a working idempotency guarantee (a repeat call returns the
   same `deterministic_run_id` without re-executing).
2. **Nothing is fabricated to look complete.** The one section that isn't
   `PRODUCED` (`ais`) isn't produced because the fixture genuinely has zero
   tracks — not because of an integration defect papered over.
3. **Provenance is honest at two levels simultaneously** — `engine_mode` and
   `evidence_mode` — which is the harder and more useful property than
   either one alone.
4. **PRAMAN independently verifies** the run's registered artifact
   (`workflow.praman.verify(artifact_id) is True`), so the "complete case
   result" claim is not just self-reported by the pipeline that produced it.
