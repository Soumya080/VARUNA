# Case Orchestration Reconciliation — Report

This report covers the "VARUNA GRID v2 — ORCHESTRATION RECONCILIATION" task
as it landed in *this* session. Its primary deliverable —
`packages/varuna_domain/golden_case_engine.py`, the canonical case runner
unifying `CaseWorkflow` and `RealE2EPipeline` — was already built, tested and
committed by a peer session (`router-datasets-65`, commit `5e15419`) before
this session's copy of the task arrived. Rather than build a second,
competing engine (the exact failure mode the task explicitly forbids), this
session verified that work, added the one piece its own report flagged as an
open gap, and produced the two artifacts the task named that did not yet
exist at the paths it specified.

**Read `reports/cases/GOLDEN_CASE_ENGINE_REPORT.md` first.** It is the
implementation record: what was built, the full test list, the fixture
contents, the coordination history, and the Limitations section this report
does not repeat. This report exists to (a) independently confirm that work
rather than take it on trust, (b) document the one addition made on top of
it, and (c) state the final status this task asks for.

## What existed before this task

Two orchestration surfaces, neither aware of the other, each built by a
different session earlier in this same multi-session effort:

- `varuna_domain.CaseWorkflow` — lifecycle (`CaseStatus`), persistence,
  PRAMAN artifact registry, event spine. Takes slick points as input; no
  detection stage; synthetic forcing.
- `varuna_integration.RealE2EPipeline` (this session's own earlier work,
  "Track 4") — ten real producer stages, `NetraDetectionBoundary` freeze
  gate, real ERA5/CMEMS forcing, real AIS, `EvidenceMode` propagation. No
  lifecycle, no persistence, no idempotency, non-deterministic `run_id`.

## What was reused, verified independently

`router-datasets-65`'s `GoldenCaseWorkflow` (`packages/varuna_domain/
golden_case_engine.py`, `packages/varuna_domain/replay_fixtures.py`,
`CaseStatus` extended additively in `entities.py`) reuses both surfaces
unmodified: `RealE2EPipeline.run()` is called as a black box; `Case`,
`CaseRepository`, `PramanService`, `EventSpine` are reused directly. This
session did not take that summary on trust — it was checked:

- `git show --stat 5e15419` — confirmed the commit is real, additive
  (8 files, 1875 insertions, 0 deletions), and touches none of this
  session's own files (`varuna_integration/`, `operator_case_view.py`,
  `docs/e2e/`).
- Ran the full suite this session had not previously run in one pass:
  `tests/unit` + `tests/integration/test_track4_mc20_e2e.py` +
  `tests/integration/test_golden_case_engine_mc20_e2e.py` + `tests/contract`.
  **546 passed, 4 skipped, 1 pre-existing failure** (see below), 1 warning.
- Read `golden_case_engine.py` directly rather than rely on the peer's
  description — the lifecycle mapping (`STAGE_TO_STATUS`, `derive_case_status`),
  the idempotency cache (`_cached_result`, keyed on `(case_id, config_hash)`),
  and the `preprocessing_version` handling (`detector_provider_info()`,
  explicitly labelled `ASSUMED_NETRA_PREPROCESSING_VERSION` rather than
  presented as measured) all match what was reported.

**The one pre-existing, unrelated failure:**
`tests/unit/test_netra_training.py::test_netra_training_loop` —
`TypeError: 'NetraSample' object is not subscriptable` in
`packages/varuna_netra/training/trainer.py`. This is inside NETRA training
code, explicitly off-limits to this task ("DO NOT TOUCH NETRA TRAINING"), and
unrelated to case orchestration. Not investigated further and not fixed here;
flagged for whoever owns that file.

## What was changed by this session

One addition, confined to `golden_case_engine.py`, closing the single gap
`65`'s own report named as open rather than silently assumed covered:

**`deterministic_run_id()`** — a new function plus a new field on
`ReproducibilityRecord`. `PipelineRun.run_id` remains exactly what it was
(`RUN-{datetime.now()}-{uuid4().hex[:6]}`, inside
`varuna_integration.pipeline`, untouched) — an execution-instance identifier,
left alone because reshaping it would ripple into every existing report and
test that reads it. `deterministic_run_id(case_id, engine_mode, config_hash,
model_version, dataset_version)` is a SHA-256 over exactly those five
values — a pure function of the canonical case inputs, configuration, model
version and dataset version, with no wall-clock or randomness input. Verified
directly, not just asserted:

```
deterministic_run_id('CASE-X','real','abc123','netra-v0.2-baseline','ds-1')
  == deterministic_run_id('CASE-X','real','abc123','netra-v0.2-baseline','ds-1')   # True
  != deterministic_run_id('CASE-X','real','abc123','netra-v0.2-baseline','ds-2')   # True
```

`started_at`/`finished_at` remain where wall-clock execution time is
recorded on `ReproducibilityRecord`, per the task's instruction to keep that
separate from identity. This closes the distinction between **idempotency**
(a repeated call must not re-execute or duplicate side effects — already
correct, keyed on `(case_id, config_hash)`) and **run identity** (a stable
name for "this configuration of this case" independent of when it ran — the
part that was still missing).

All 66 golden-engine tests (`test_golden_case_engine.py`,
`test_golden_case_engine_fail_closed.py`, `test_replay_fixtures.py`,
`test_golden_case_engine_mc20_e2e.py`) pass against this change, in addition
to the full 546-pass run above.

## What was created at the paths this task specified

- `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md` — did not exist
  before this task (the content it asks for existed, but inside `65`'s
  report, at a different path). Written as a genuine architecture reference —
  the full responsibility-ownership table, a Mermaid call graph, the
  three-vocabulary state model with the reasoning for keeping them separate,
  the real/simulated boundary, the three-layer provenance flow, the
  idempotency-vs-run-identity distinction, and the model-contract gap — not a
  bare pointer, though it defers to the report for implementation detail
  rather than duplicating it.
- This file, at the exact path the task named.

## Canonical call graph (summary — full diagram in the architecture doc)

```
case_id + config
  → GoldenCaseWorkflow.run_case()
    → (cached? return CaseResult) or RealE2EPipeline.run()
      → forcing → ais_ingest → netra_detection → phi_reconstruction
        → attribution → validity → forecast → decision → mission → alerts
    → _finalize(): CaseStatus transition, ReproducibilityRecord
      (+ deterministic_run_id), PRAMAN artifact, event emit
  → CaseResult.to_operator_case() → OperatorCase v1
```

`run_replay_case()` follows the identical path from `_finalize()` onward,
substituting a canned `PipelineRun` from `replay_fixtures` for the pipeline
call — the guarantee that REPLAY is not a second pipeline.

## State model

Three vocabularies, preserved separately, per the task's explicit instruction
not to collapse them:

- **`StageStatus`** (`PRODUCED`/`NOT_YET_PRODUCED`/`BLOCKED`) — did the stage
  execute.
- **`ValidityState`** (`VALID`/`DEGRADED`/`RESTRICTED`/`INCONCLUSIVE`) — what
  the gate concluded. All four preserved; `DEGRADED` and `INCONCLUSIVE` are
  not in the abbreviated `VALID/RESTRICTED/BLOCKED/UNAVAILABLE` list some
  task prompts use as shorthand — that list is a subset of this enum's real
  states, not a replacement for it.
- **`EvidenceMode`** (`REAL`/`SIMULATED`/`UNAVAILABLE`) — how real the input
  was. Monotonic-worsening only.
- **`CaseStatus`** — the lifecycle layer that was genuinely missing before
  this reconciliation; a projection of `StageStatus` outcomes onto a case's
  life, not a fifth independent vocabulary.

Full detail and the reasoning for keeping them separate: architecture doc §4.

## Idempotency and run identity

- **Idempotency**: `(case_id, config_hash)`-keyed cache in
  `GoldenCaseWorkflow._cached_result()`. A repeated `run_case()` call with an
  equal config returns the prior `CaseResult` — same missions, same alerts —
  unless `force=True`. Built by `65`, verified by this session's test run,
  unchanged.
- **Run identity**: `deterministic_run_id()`, added by this session (above).

## Model contract

Verified before real inference (unchanged, built earlier this session):
checkpoint hash against a `.frozen.json` sidecar, architecture/encoder/
channel cross-check against the sidecar's own `model_spec`, `model_version`/
`dataset_version`/`experiment_id`/`scientific_status` read from the sidecar.

**Not verified anywhere: preprocessing compatibility.** No
`preprocessing_version` field exists on `NetraModelSpec`; nothing asserts a
checkpoint's expected normalization matches what the Gold pipeline actually
produced. `golden_case_engine.py` reports
`ASSUMED_NETRA_PREPROCESSING_VERSION = "netra-norm-v0.2-nodata-excluded"`,
explicitly labelled ASSUMED — a case-engine convenience note, not enforcement.
**This is the single most consequential open gap.** A checkpoint trained on
differently normalized tiles would also detect nothing on MC20, and nothing
in this pipeline today would distinguish that from the genuine MC20 domain
gap. This was surfaced, not closed — adding real enforcement means adding
`preprocessing_version`/`normalization_version`/`channel_mapping_version` to
`NetraModelSpec` and rejecting a mismatch at `resolve_netra_boundary()`,
which touches the detector boundary this session owns but was not done here
because it is a scientific-contract change, not an orchestration-reconciliation
one, and doing it unreviewed inside this task would risk exactly the kind of
silent scope creep the task's own rules warn against.

## Provenance flow

Three layers — stage-level (`case_bridge.apply_run_to_case`), run-level
(`ReproducibilityRecord`), case-level rollup
(`operator_case_view._provenance()`, additive merge of the PRAMAN registry
with stage-reported provenance). Full detail: architecture doc §6. Unchanged
by this session except for the new `deterministic_run_id` field flowing
through layer 2.

## MC20 real behavior

Unchanged from this session's earlier Track 4 work, and re-confirmed still
true by `65`'s integration tests: NETRA detects nothing on real MC20 (all 9
tiles, zero pixels above threshold). The canonical REAL MC20 case correctly
demonstrates observation → NETRA OOD result → safe downstream handling
(`NOT_YET_PRODUCED` with named reasons through phi/attribution/validity/
forecast/decision/mission/alerts) → explicit evidence/validity states. No
fixture anywhere shows MC20 reaching a valid detection or mission dispatch —
producing one would be fiction, per this task's own instruction.

## Remaining gaps

1. **`preprocessing_version` enforcement** — named above, not closed.
2. **`varuna_domain.CaseWorkflow.reconstruct()` still runs synthetic
   forcing** on its own, separate, still-present entry point (not
   `GoldenCaseWorkflow`) — a disclosed architectural split, not a defect;
   see architecture doc §5.
3. **Mission cancellation for AVAILABLE/RESERVED missions** and
   **CRITICAL alert severity being unreachable by design** — both
   pre-existing, flagged by `router-datasets-3f`'s parallel mission/alert
   reconciliation, both correctly left as open product/ADR decisions rather
   than silently worked around.
4. Everything `65`'s own report lists under its Limitations section —
   not re-derived here.

## Test results (this session's verification pass)

```
tests/unit + tests/integration/test_track4_mc20_e2e.py +
tests/integration/test_golden_case_engine_mc20_e2e.py + tests/contract
  546 passed, 4 skipped, 1 failed (pre-existing, unrelated, NETRA training)

tests/unit/test_golden_case_engine.py +
tests/unit/test_golden_case_engine_fail_closed.py +
tests/unit/test_replay_fixtures.py +
tests/integration/test_golden_case_engine_mc20_e2e.py
  66 passed (re-run in isolation after the deterministic_run_id addition)
```

## Safety

```
deleted = 0
moved = 0
renamed = 0
overwritten = 0
```

Verified via `git status --porcelain` (no `D`/`R` entries) both before and
after this session's addition. MC20 Gold manifest mtime unchanged
(2026-08-30 00:28, predates this session's activity today). NETRA training,
checkpoints, and Gold untouched.

## FINAL STATUS

**CASE_ORCHESTRATION_READY**

Qualified: ready for the orchestration surface itself — one canonical engine
exists, verified, with lifecycle, persistence, idempotency, deterministic run
identity, and correct real/simulated separation. Not qualified as "the MC20
domain gap is resolved" (it isn't, and resolving it is out of this task's
scope) or as "preprocessing compatibility is enforced" (it isn't — see
above, the most important open item this task surfaced).
