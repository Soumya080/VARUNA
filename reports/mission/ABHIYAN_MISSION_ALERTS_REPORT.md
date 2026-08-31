# VARUNA GRID v2 — ABHIYAN / Mission / Alert Operational Workflow Report

## Scope and starting state

This was **not** a from-scratch build. Track 4 (a concurrent session,
`router-datasets-ca`) had already implemented the substance of ABHIYAN →
Mission → Alerts inside `packages/varuna_integration/pipeline.py`
(`_decide` / `_mission` / `_alerts`), fail-closed by construction:

- ABHIYAN is only ever called after the validity stage has produced a real
  `ValidityGateResult`, and `gate.state` is passed straight into
  `AbhiyanService.plan_mission()`, which itself refuses to plan when
  `not gate_state.allows_operational_action`.
- Missions are created `AVAILABLE` (PROPOSED) only — the pipeline never
  calls `approve_and_assign()`, and the code carries an explicit comment
  that authorization is left to a human operator.
- Alerts route through the real `AlertService`, which already enforces
  materiality (`check_materiality` withholds any alert when
  `not gate_state.allows_operational_action`), freshness, and dedupe
  (`DedupeWindow`, keyed by `case_id:event_type:recipient`).

This report's job was therefore: (1) verify those fail-closed claims
independently rather than take them on trust, (2) add the specific
vocabulary this task asked for (`VALID/RESTRICTED/BLOCKED/UNAVAILABLE`
decision states, a mission-lifecycle mapping, alert severity) **as views
over the existing, locked contracts**, not as competing new ones, and
(3) fix one real, pre-existing defect this work uncovered along the way.

Before touching anything, this session coordinated with two peer sessions
(`router-datasets-ca`, owner of `pipeline.py`/`operator_case_view.py`, and
`router-datasets-65`, starting a "Golden Case Engine" task touching the same
orchestration surface) to confirm no active edits collided. Both confirmed
clear.

## Decision states — VALID / RESTRICTED / BLOCKED / UNAVAILABLE

**Not implemented as a new state machine.** The four labels are, precisely,
three different existing vocabularies collapsed into one convenience view:

| requested label | source of truth |
|---|---|
| VALID, RESTRICTED | `ValidityState` (`varuna_contracts/evidence.py:80`) — did the gate run and what did it conclude |
| BLOCKED | `StageStatus.BLOCKED` (`varuna_integration/stage.py`) — did the stage fail to execute |
| UNAVAILABLE | absence of a gate result, or `ValidityState.INCONCLUSIVE` — was there evidence to evaluate at all |

Implemented in `packages/varuna_abhiyan/decision_state.py` as
`derive_operational_decision_state(gate, *, validity_stage_failed=False)`,
returning `varuna_contracts.operator_case.OperationalDecisionState`. Mapping:

- `ValidityState.VALID`, `ValidityState.DEGRADED` → **VALID**
- `ValidityState.RESTRICTED` → **RESTRICTED**
- `ValidityState.INCONCLUSIVE`, or `gate is None` → **UNAVAILABLE**
- `validity_stage_failed=True` (a genuine pipeline crash) → **BLOCKED**

**The task's four-label list silently drops `ValidityState.DEGRADED` and
`ValidityState.INCONCLUSIVE`.** Both remain first-class, fully visible
outcomes on `OperatorCase.validity` (the real `ValidityGateResult`, with its
own `state`, `checks`, `blocking_reasons`, `officer_visible_caveats`) — this
derived enum is a **subset view for a caller that wants the smaller
vocabulary, not a replacement**. DEGRADED specifically was kept mapped to
VALID rather than RESTRICTED: DEGRADED means "actionable with caveats shown
to the officer" — folding it into RESTRICTED would refuse an action the
system has determined is legitimately allowed, and folding it silently into
VALID (without keeping the real `ValidityGateResult` reachable) would hide
the caveats. Neither is acceptable, so both are preserved: `recommendation`
gives the four-way bucket, `validity` gives the full picture.

A critical subtlety, caught and tested explicitly
(`test_recommendation_distinguishes_restricted_gate_from_stage_crash`):
`apps/api/operator_case_view.py`'s `_validity_section()` maps a
**successfully-evaluated RESTRICTED gate** to `ProducerStatus.BLOCKED` on
the `validity` `SectionEnvelope` (an intentional Track-2/OperatorCase-era
decision: "the gate ran and said no"). That is a **completely different
claim** from `OperationalDecisionState.BLOCKED` (a genuine execution
failure). `_recommendation()` deliberately does NOT read `validity.status`
for this reason — it reads the pipeline's own raw `StageStatus` (via
`case.metadata["validity_section"]`, written by
`varuna_integration.case_bridge`) so the two `BLOCKED`s are never
conflated.

## Mission lifecycle

**Not implemented as a new FSM.** `MissionState` and `MISSION_TRANSITIONS`
(`varuna_contracts/states.py`, "changing anything here requires an ADR")
remain the only stored state. `packages/varuna_missions/lifecycle_view.py`
documents the mapping as a table (not a 1:1 equivalence) and adds two
read-only predicates for the two labels that have no stored equivalent:

| requested label | MissionState / derived predicate |
|---|---|
| PROPOSED | `AVAILABLE`, `human_approved_by is None` |
| REVIEW_REQUIRED | derived, same as PROPOSED — `is_review_required()` |
| APPROVED | `ASSIGNED`, gated behind `human_approved_by` |
| DISPATCHABLE | derived, same as APPROVED — `is_dispatchable()` |
| DISPATCHED | `EN_ROUTE` |
| COMPLETED | `COMPLETE` |
| BLOCKED | not a `MissionState` at all — a `StageStatus.BLOCKED` fact about the *pipeline stage*, not a state any `MissionRecord` is ever in (a record only exists once already proposed) |
| CANCELLED | **no clean equivalent — see below** |

**Fail-closed proof (no automatic advance), verified by test, not just by
reading the code:**
`test_mission_created_from_tasking_is_proposed_not_assigned` and
`test_mission_cannot_advance_to_assigned_without_human_approval` —
`MissionRecord.transition(ASSIGNED)` raises `ValueError` without a named
`human_approved_by`, and a freshly-created mission is always `AVAILABLE`
with `human_approved_by=None`. `RESTRICTED → DISPATCHED` and
`BLOCKED → DISPATCHABLE` cannot happen automatically because no code path
anywhere calls `approve_and_assign()` without an explicit, named human
argument, and a `RESTRICTED`/`BLOCKED` gate produces zero taskings in the
first place (see below) — there is nothing to approve.

### Mission cancellation policy gap (genuine, unresolved)

`MISSION_TRANSITIONS` has **no path from `AVAILABLE` or `RESERVED` to
`CLOSED`**. A mission that is still PROPOSED/REVIEW_REQUIRED (i.e. never
approved) **cannot be cancelled** in the current locked FSM — there is no
transition sequence that reaches a terminal state from there.
`cancel_mission()` raises `MissionNotCancellableError` for this case rather
than fabricating a transition, silently no-op'ing, or working around the
lock. For a mission already `ASSIGNED` or later, `REASSIGNED → CLOSED` is a
legal path and `cancel_mission()` uses it as an interim proxy for
"cancelled" — both are verified by test
(`test_cancel_proposed_mission_raises_named_gap_error`,
`test_cancel_assigned_mission_uses_reassigned_then_closed`).

**This requires a decision from a science/product owner, not a code fix**:
either (a) an ADR adding a legal `AVAILABLE`/`RESERVED → CLOSED` edge (or a
genuine `CANCELLED` state) to `varuna_contracts/states.py`, or (b) an
explicit product decision that an unapproved mission proposal is simply
deleted/discarded rather than state-transitioned (which the current
`MissionRepository` interface doesn't support either — there is no
`delete()`). Not resolved in this task, by design — see the task's own
"if underspecified, document the decision needed" instruction.

## A real, pre-existing defect found and fixed

`MissionService.approve_and_assign()` (`packages/varuna_missions/service.py`)
called `m.transition(MissionState.ASSIGNED)` directly from a freshly-created
mission's `AVAILABLE` state. `MISSION_TRANSITIONS[AVAILABLE]` only permits
`{RESERVED}` — there is **no direct `AVAILABLE → ASSIGNED` edge**. This
made the very first approval of any pipeline-created mission raise
`ValueError: illegal mission transition available -> assigned`, before ever
reaching the `human_approved_by` check. Fixed by inserting the
already-legal `AVAILABLE → RESERVED` step first (skipped if the mission is
already `RESERVED`, so a re-approval isn't double-transitioned). Verified
with `test_approve_and_assign_requires_named_human` and
`test_cancel_assigned_mission_uses_reassigned_then_closed`, both of which
failed before the fix and pass after it. This was not introduced by this
task — it predates this session and was simply never exercised by an
existing test until now.

## Alerts

**Severity policy gap — resolved exactly as the task instructed.**
`INFO`/`WARNING`/`BLOCKED`/`CRITICAL` is now a real vocabulary
(`varuna_contracts.operator_case.AlertSeverity`), but no urgency-scoring
policy exists anywhere in this codebase (checked
`materiality.py`/`freshness.py`/`role_router.py`/`templates.py` — none of
them score how urgent a real spill event is). Per the task's explicit
instruction ("do not invent safety-critical severity rules... if missing,
document policy gap"), `varuna_alerts/severity.py::infer_severity()`
computes **only** the two facts already known — was the send suppressed,
did it reach a simulated channel — and **never produces `CRITICAL`**
(proven exhaustively by `test_critical_severity_is_never_produced_by_infer_severity`
over its entire boolean input space). Assigning `CRITICAL` requires a real
urgency policy (spill volume, shoreline ETA, asset proximity, ...) that a
science/product owner has not defined; inventing one here would have been
exactly the fabrication the task prohibits.

**Deduplication** already existed and needed no new code:
`varuna_alerts.dedupe.DedupeWindow`, keyed by the deterministic
`f"{case_id}:{event_type}:{recipient}"` scheme in
`AlertService.route_and_send()`. Verified by test that the same key is a
duplicate on a second send within the window, and that a different case,
event, or recipient is never treated as one.

**`AlertView`** (the `OperatorCase.alerts` value type) gained `category`
(the routed `event_type`, honestly `None` when not available — deliberately
NOT reconstructed by parsing a channel-specific `idempotency_key` format,
which varies per channel and would be a fragile guess) and `severity`. A
one-line additive change to `varuna_integration/pipeline.py`'s `_alerts`
stage now records `event_type` in the stage's own `detail` dict so
`category` can be read honestly instead of always being `None`.

**SIMULATED cannot silently become REAL**, re-verified for alerts
specifically: `infer_severity(is_simulated=True)` always returns `WARNING`,
never `INFO` — proven for every combination of `suppressed`/`is_simulated`
(`test_simulated_alert_severity_never_reads_as_info`). This sits alongside
the pre-existing, independently-verified guarantee in
`_delivery_status()` (`apps/api/operator_case_view.py`) that a "sent"
result on a simulated channel maps to `AlertDeliveryStatus.SIMULATED`, never
`DELIVERED`.

## Fail-closed proofs (all test-verified, not just read)

| Rule | Proof |
|---|---|
| `validity = BLOCKED` (stage crash) → no mission | `test_recommendation_is_blocked_only_for_a_real_pipeline_stage_failure`; `_mission()` in pipeline.py checks `decision_res.produced` before creating any `MissionRecord`, and `decision_res` is itself never `PRODUCED` off a failed validity stage |
| `validity = RESTRICTED` → no automatic dispatch | `test_restricted_gate_produces_zero_tasking_even_with_valid_search_boxes` — proven with a real, well-formed `SearchBox` that DOES produce tasking under `VALID` (`test_valid_gate_with_real_inputs_does_produce_tasking`), so this isn't a fixture that would return `[]` regardless of gate state |
| `evidence = UNAVAILABLE` → no fabricated mission | `test_no_gate_is_unavailable_not_blocked` (`gate=None → UNAVAILABLE`); `_mission_section` in `operator_case_view.py` reports `NOT_YET_PRODUCED`, never a fabricated empty-but-"produced" mission list, when no decision value exists |
| `evidence = SIMULATED` cannot silently become REAL | `test_simulated_alert_severity_never_reads_as_info`; the pre-existing `EvidenceMode` monotonic-worsening guarantee (`EvidenceEnvelope.derive()`, ADR-0006) is untouched by any change in this task |

## OperatorCase wiring

`OperatorCase` (`packages/varuna_contracts/operator_case.py`) gained one new
required field:

```python
recommendation: OperationalDecisionState
```

Always computable (even "no gate ran" is a defined answer — `UNAVAILABLE`),
so unlike the other sections it is not wrapped in a `SectionEnvelope`.
`mission`, `alerts`, and `validity` were already exposed
(`OperatorCase.mission`, `.alerts`, `.validity`) from the earlier Track 4
work; this task added `severity`/`category` to `AlertView` and the new
`recommendation` field. `GET /v1/cases/{case_id}/operator-view` needed no
endpoint change — it already serializes whatever `build_operator_case()`
returns.

## Replay examples

Deterministic examples were built as **tests**, not as fixture files
claiming to be full E2E cases — per `router-datasets-ca`'s finding
(independently confirmed, not re-litigated here): on the real MC20 path,
NETRA currently detects nothing (all 9 tiles, zero pixels above threshold),
so `decision`/`mission`/`alerts` legitimately never fire on that path today,
and any fixture depicting a full real-MC20 chain reaching dispatch would be
fiction. The five requested scenarios are covered by direct, fast unit
tests instead (`tests/unit/test_mission_alerts_decision.py`):

- **strong valid** → `test_valid_gate_with_real_inputs_does_produce_tasking`, `test_decision_state_mapping[VALID]`
- **weak/degraded attribution** → `test_degraded_is_not_folded_into_restricted`
- **blocked** → `test_recommendation_is_blocked_only_for_a_real_pipeline_stage_failure`
- **unavailable** → `test_no_gate_is_unavailable_not_blocked`, `test_decision_state_mapping[INCONCLUSIVE]`
- **simulated** → `test_simulated_alert_severity_never_reads_as_info`, `test_alert_severity_is_structural_only[False-True-WARNING]`

## Files created

- `packages/varuna_abhiyan/decision_state.py`
- `packages/varuna_alerts/severity.py`
- `packages/varuna_missions/lifecycle_view.py`
- `tests/unit/test_mission_alerts_decision.py` (26 tests)
- `reports/mission/ABHIYAN_MISSION_ALERTS_REPORT.md` (this file)

## Files modified

- `packages/varuna_contracts/operator_case.py` — added `AlertSeverity`,
  `OperationalDecisionState`; `AlertView` gained `category`/`severity`;
  `OperatorCase` gained `recommendation`.
- `packages/varuna_contracts/__init__.py` — exported the two new enums.
- `apps/api/operator_case_view.py` — `_alerts_section` computes
  `category`/`severity`; new `_recommendation()`; wired into
  `build_operator_case()`.
- `packages/varuna_integration/pipeline.py` — one-line additive: `_alerts`
  stage records `event_type` in its `detail` dict.
- `packages/varuna_missions/service.py` — fixed the pre-existing
  `approve_and_assign()` illegal-transition defect (see above).
- `tests/contract/test_operator_case.py` — `_minimal_operator_case()` helper
  updated for the new required `recommendation` field.

## Test results

```
tests/contract                              (83 passed, includes 19 OperatorCase contract tests)
tests/unit/test_mission_alerts_decision.py  (26 passed — new this task)
tests/unit/test_track4_boundaries.py        (29 passed)
tests/integration/test_track4_mc20_e2e.py   (23 passed)
tests/unit/test_missions_mock.py            (3 passed — pre-existing, unaffected by the FSM fix)
tests/e2e/test_m4_full_pipeline.py          (1 passed — pre-existing, unaffected)
tests/unit/test_validity_gate.py            (14 passed)
tests/api                                   (5 passed)
------------------------------------------------------------
176 passed, 0 failed
```

No production-scale run, no MC20 Gold read, no NETRA inference was executed
by this task — every test above runs in well under a minute on synthetic,
directly-constructed contract objects.

## NETRA isolation

`nvidia-smi` showed 90–100% GPU utilization throughout this session
(NETRA training active in a separate workstream). No file under
`packages/varuna_netra/**`, `train_netra.py`, or `configs/lab/netra*.yaml`
was read or written by this task.

## Data safety

deleted = 0, moved = 0, renamed = 0, overwritten = 0.

## Remaining gaps (explicit, not silently worked around)

1. **Mission cancellation for PROPOSED/REVIEW_REQUIRED missions** — no
   legal FSM path exists; needs an ADR or a product decision (see above).
2. **Alert `CRITICAL` severity** — no assignment policy exists anywhere in
   this codebase; `infer_severity()` can never produce it. A science/product
   owner needs to define an actual urgency policy before `CRITICAL` can be
   assigned to anything.
3. **`AlertView.category`** is `None` for any case that predates this
   task's one-line `pipeline.py` change, or for alerts assembled outside
   the `varuna_integration` pipeline entirely.
4. **On the real MC20 path, NETRA currently detects nothing** — this is a
   pre-existing, independently-confirmed fact (not discovered by this
   task), and means `decision`/`mission`/`alerts` have not yet fired on an
   actual real-evidence case. Nothing in this task's scope changes that.

---

**MISSION_ALERTS_READY**
