# ADR-0012: Surface `engine_mode` on `OperatorCase.system_status`

**Status:** Accepted
**Date:** 2026-09-02
**Session:** VARUNA GRID v2 — STEP 2, POPULATED CANONICAL REPLAY E2E

## Context

`GoldenCaseWorkflow._finalize()` already computes and records `engine_mode`
(`REAL` / `REPLAY` / `SIMULATED`, from `varuna_domain.golden_case_engine.EngineMode`)
on every `ReproducibilityRecord` it produces — this is not new data, it exists
today. It is stored at `case.metadata["golden_engine_runs"][cfg_hash]["reproducibility"]["engine_mode"]`.

**It never reaches `OperatorCase`.** `apps.api.operator_case_view.build_operator_case()`
does not read it, and `varuna_contracts.operator_case.OperatorCase` has no
field for it. Every per-section `SectionEnvelope.evidence_mode` is one of
`REAL` / `SIMULATED` / `UNAVAILABLE` (`varuna_contracts.evidence.EvidenceMode`)
— a genuinely different axis, answering "how real is this evidence" rather
than "how was this run executed."

The consequence, found by tracing `CASE-VALID`'s actual execution (STEP 2,
Phase 1): every stage in that replay fixture is deliberately stamped
`EvidenceMode.REAL` (see `packages/varuna_domain/replay_fixtures.py::_build_valid`,
whose own comments call every value "SYNTHETIC like every other number in
this file"). That is not itself dishonest — it models what REAL evidence
would look like if a frozen, calibrated checkpoint had fired — **but only if
the fact that this run was REPLAYED, not live, is visible somewhere else.**
Today it is not visible anywhere in `OperatorCase`. A consumer of the
canonical product projection sees `evidence_mode: real` on every section and
has no way to learn this was a canned fixture rather than a live inference
run, unless they reach past the contract into `case.metadata` directly —
which `OperatorCase` exists specifically to avoid requiring.

This is exactly the failure STEP 2's Phase 7 instruction names: *"Do not
convert replay to REAL just because the replay contains recorded real-world
values."* The values were never converted — `EvidenceMode.REAL` was the
fixture's own honest label for what it models — but the run's REPLAY-ness
was silently dropped on the way to the one contract a consumer actually
reads.

## Decision

Add `engine_mode: str | None = None` to `varuna_contracts.operator_case.SystemStatusView`.
`None` for any case produced by the legacy `CaseWorkflow` path (which has no
such concept — additive, breaks nothing for existing callers). A real string
value (`"real"` / `"replay"` / `"simulated"`) for any case produced by
`GoldenCaseWorkflow`.

Plumbing: `GoldenCaseWorkflow._finalize()` additionally writes
`case.metadata["engine_mode"] = mode` (a flat, always-current key — not
nested under the idempotency cache's `golden_engine_runs`, since a consumer
wants "what produced this case's current state," not a historical index).
`build_operator_case()` reads `case.metadata.get("engine_mode")` — a
dict-key read on an entity `operator_case_view.py` already receives, no new
parameter, no signature change.

## Consequence

`OperatorCase.system_status.engine_mode` and
`OperatorCase.<section>.evidence_mode` now answer two different, both
necessary questions side by side: *how was this case executed* and *how real
is this section's evidence*. Neither can silently stand in for the other.
`REPLAY` + `REAL` together mean exactly what `CASE-VALID` intends: "this
models what a real, successful case's evidence looks like; it was not,
itself, live."

## Alternatives considered

- **Add `engine_mode` to `EvidenceMode` itself** (four values instead of
  three) — rejected: conflates two orthogonal questions this repository has
  repeatedly kept separate on purpose (`StageStatus` / `ValidityState` /
  `EvidenceMode` per `docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md`
  §4). `EngineMode` already exists as its own three-value enum for exactly
  this reason; reusing it rather than inventing a fourth `EvidenceMode` value
  is the smaller, more consistent change.
- **Change `build_operator_case()`'s signature** to take `engine_mode`
  explicitly — rejected: would require every existing caller (4 production
  sites, 6 test/script sites per `docs/product/CANONICAL_WORKFLOW_POLICY.md`
  §3.1) to be touched. Reading an already-present `case.metadata` key is
  strictly additive.
