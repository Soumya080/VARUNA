# ADR-0016 — "Verified" is a 5-axis ledger, not `InvestigationState.VERIFIED`

**Status:** Accepted
**Date:** 2026-09-04
**Related:** Phase 6B of the correctness/story audit, docs/product/HONESTY_LEDGER.md #19

## Context

The frontend needed an honest answer to "what does 'verified' mean in this
system?" — the fake linear mission track it used to show (see ADR/plan
history around Phase 6A) ended at a step literally labelled `VERIFIED`,
implying a producer for that word existed. It didn't.

`InvestigationState.VERIFIED` (`packages/varuna_contracts/states.py:43`) is
the only real "verified" enum value anywhere in the codebase. Grepping every
reference to `InvestigationState.VERIFIED` and `InvestigationState.TRIAGED`
across `apps/`, `packages/`, and `scripts/` finds **zero production call
sites** — the enum exists, is exported, and is never constructed by any real
pipeline stage. Nothing in the replay path, the golden engine, or the
operational loop ever transitions a case into `VERIFIED`.

## Decision

Do **not** wire `InvestigationState.VERIFIED` into the frontend by
synthesising a producer for it. Doing so would require inventing logic that
decides "this case counts as verified now" — exactly the class of
fabrication Phase 2 of this same audit was removing elsewhere (M1/M2: a
fabricated `CandidateScore` presented as computed). Adding one invented
status while deleting another would be incoherent within the same body of
work.

Instead, "verified" is decomposed into **five independently real,
independently producible confirmation signals** that already exist in the
system, surfaced via `components/verification-ledger.tsx`:

| Axis | Real producer |
|---|---|
| Physical confirmation | `MissionRecord.state` reaching `CONTACT -> CONFIRMED` |
| Human authorization | `MissionRecord.human_approved_by` (server-enforced: `ASSIGNED` cannot be reached without it — `varuna_contracts/states.py`'s own transition guard) |
| Evidence gate | `ValidityGateResult.state` in `{valid, degraded}` (`allows_operational_action`) |
| Operator action | `AlertLifecycleRecord.status` reaching `acknowledged`/`resolved`, with the acting principal from its own transitions |
| Historical outcome | SMRITI `CaseMemory.outcome` for the case's own record (`GET /v1/cases/{id}/memory-outcome`, new this session) |

The header reads `Verification: N of 5 axes confirmed`. An axis with no
evidence yet renders `NOT_YET`, never blank or omitted — an unconfirmed axis
is a real, honest state, not an error to hide.

## Why this is more defensible, not a workaround

A single `VERIFIED` badge invites exactly one follow-up question a judge or
auditor will ask: *"verified by what, exactly?"* A badge with an invented
producer has no honest answer. Five named, independently-checkable axes,
each pointing at a real field with a real write path, does. This is also
strictly more informative: a case can be evidence-gated VALID and
operator-acknowledged while still lacking physical confirmation (the asset
hasn't reached the contact yet) — collapsing that into one boolean would
lose the distinction that actually matters operationally.

## Path to wiring `InvestigationState.VERIFIED` later

Not abandoned — deferred honestly. `InvestigationState.VERIFIED` becomes
producible once a mission genuinely reaches `MissionState.CONFIRMED` **and**
carries a real `human_approved_by` — i.e., once axes 1 and 2 of the ledger
above are both true for the same case. At that point, a case-level
transition function could construct `InvestigationState.VERIFIED` from that
conjunction and the enum would finally have a real call site. Until that
function exists, treating `VERIFIED` as reachable would be fiction with
extra steps.

## Consequences

- No new invented state; no new backend fabrication.
- The ledger is one more thing to keep in sync if a 6th confirmation signal
  is ever added — acceptable cost for not lying about the 5 that exist.
- `InvestigationState.VERIFIED` remains unused. That is now documented
  as an intentional, temporary gap rather than an unnoticed one.
