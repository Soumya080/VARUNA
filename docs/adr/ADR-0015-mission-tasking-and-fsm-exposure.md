# ADR-0015 — Mission tasking on `MissionRecord`, and exposing the mission FSM

**Status:** Accepted
**Date:** 2026-09-03
**Supersedes:** nothing. **Related:** ADR-0012 (engine_mode), ADR-0013 (composition boundary)

## Context

`varuna_contracts` is a locked package: its own docstring requires an ADR for
any change. Two findings force one.

**1. The tasking is computed and then thrown away.**
`MissionService.create_mission(case_id, asset_id, tasking)` accepts an
`AssetTasking` — search box, pattern, launch time, flight hours,
probability of detection, rationale — and never stores it. `MissionRecord`
has no field for it. ABHIYAN genuinely computes that tasking in the pipeline
decision stage (`varuna_integration/pipeline.py:640-648`), it reaches
`_mission()`, and it is discarded at the door. Consequences:

- A mission carries `asset_id` only, which is a *base name* string like
  `"INS Replay Base"`. Nothing records where the asset should actually go.
- A map UI has nothing to draw for a mission — no search box, no pattern.
- An operator authorising a dispatch cannot see what they are authorising.
- Several call sites already pass `tasking=None`, which nothing objects to,
  because the parameter is inert.

**2. The FSM is defined but unreachable.**
`MISSION_TRANSITIONS` defines 13 states. Grepping every reference to
`ACKNOWLEDGED / EN_ROUTE / ON_STATION / SEARCHING / CONTACT / CONFIRMED /
NOT_FOUND / COMPLETE` across `apps/`, `packages/` and `scripts/` finds only
the table itself, a terminal-set check, docstrings, and tests. **No
production code and no HTTP route ever advances a mission past `ASSIGNED`.**
The frontend already renders `en_route` / `on_station` / `complete` badges
for states the system cannot produce.

A generic `MissionService.transition()` exists but has **no `authorize()`
call at all** and silently discards its `reason` argument. It is currently
unrouted, which is the only reason that is not a live authorization hole —
exposing it as-is would let anyone drive a physical asset's state machine.

## Decision

**Add `tasking: AssetTasking | None = None` to `MissionRecord`.**

Optional with a `None` default, so every existing construction site — the
replay fixtures, tests, scripts — keeps working unchanged and no persisted
record becomes invalid. `AssetTasking` already lives in
`varuna_contracts.schemas`, so this introduces no new type and no new
dependency direction.

**Add `state_change_reasons: list[tuple[str, str]]`** recording
`(state, reason)` for transitions that carry one. `state_history` already
records *when* a state changed; nothing recorded *why*. For a physical
dispatch, "why" is the more important half.

**Expose the FSM over HTTP, but only through an authorized service method.**
`MissionService.transition()` gains a **required** `principal` parameter and
calls `authorize()` before mutating — the same ordering
`approve_and_assign()` already uses, for the same reason: a permission check
after a state change leaves a partially-transitioned mission behind on
denial. `principal` is required rather than optional-with-a-default because
a defaulted authorization parameter is a fail-open.

## Alternatives rejected

**Store the tasking in `Case.metadata` instead.** Keeps `varuna_contracts`
untouched, but puts a mission's own operational payload somewhere the
mission object cannot see, and `metadata` is an untyped dict — exactly the
shape this codebase avoids for anything an operator acts on.

**A separate `MissionTasking` side-table keyed by `mission_id`.** More
faithful to a relational design, but the local stack has no database
(`USE_POSTGRES=false`), so it would mean a second JSONL store and a join for
a strictly 1:1 relationship.

**Per-verb routes (`/acknowledge`, `/en-route`, …) instead of one
`/transition`.** Ten near-identical endpoints, each a chance to forget the
authorization call. One route validating against `MISSION_TRANSITIONS` has a
single place to get right. `POST /cancel` stays separate because it is a
two-hop composite (`REASSIGNED → CLOSED`), not a single transition.

## Consequences

- `MissionRecord` gains two optional fields. Additive; no migration needed,
  and the JSONL store tolerates records written before this change.
- `MissionService.transition()`'s signature changes to require `principal`.
  It had **no production callers**, so the blast radius is
  `cancel_mission()` (updated) and tests (updated to pass a principal —
  strengthening them, since they previously exercised an unauthorized path).
- Missions become drawable on a map and reviewable before authorisation.
- Every state change past ASSIGNED is now audited, which it was not before.

## What this does NOT do

- No new mission states. The FSM in `states.py` is unchanged.
- No auto-advancement. Every transition remains operator-initiated; nothing
  moves a mission on a timer.
- No change to the two-step human approval gate. `APPROVE_MISSION` is still
  required for `ASSIGNED`, `Principal.system()` is still refused, and
  `approved_by` must still match the authorising principal.
