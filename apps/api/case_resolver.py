"""
The single place that answers "does this case_id exist, and what can I show
for it?" — replacing the ad-hoc, route-by-route guessing that caused B1.

Root cause (see docs/product/HONESTY_LEDGER.md #1 and the plan's B1 entry):
VARUNA has THREE de-facto case stores —

  1. `CaseWorkflow.cases`        (legacy, `get_workflow()`)
  2. `GoldenCaseWorkflow.cases`  (`get_golden_case_workflow()`)
  3. `replay._COMPOSED_CACHE`    (composed `OperatorCase`s, keyed by
                                  FIXTURE NAME, not case_id — the exact
                                  key-space mismatch that made
                                  `has_operator_view` computable correctly
                                  in `list_cases` — which iterates
                                  `.values()` and reads `.case_id` off each
                                  one — but unusable by every per-case route,
                                  which looked cases up by key instead)

`GET /v1/cases` already merges all three correctly. Every other case-scoped
route (`GET /v1/cases/{id}`, `/operator-view`, `/validity`, `/artifacts`, …)
consulted only store #1 — so a replay case the list happily advertised
(`has_operator_view: true`) 404'd the moment a judge clicked it.

Rejected alternatives (recorded here so they aren't tried again):
  - Merging the stores: `CaseWorkflow` and `GoldenCaseWorkflow` have
    genuinely different creation/mutation semantics (ADR-0014). Merging
    would let replay cases — which should be read-only, reproducible
    fixtures — be POST-mutated through the legacy case routes.
  - Inline `try: workflow.cases.get() except: golden.cases.get()` in every
    route: six routes × two-or-three stores is exactly the shape that
    produced this bug. One resolver, unit-tested once, used everywhere.
  - A module-level `resolve(case_id)` function that re-derives `workflow`
    by calling `dependencies.get_workflow()`/`get_case_repo()` directly:
    tried first, and reverted. `tests/integration/test_api.py` (and any
    future test) overrides `get_case_repo` via FastAPI's
    `app.dependency_overrides` to get per-test isolation; a resolver that
    bypasses FastAPI's DI and re-derives the workflow itself silently
    ignores that override and reads the process-wide singleton instead —
    a case created through the test's isolated repo then 404's when read
    back through the resolver. The fix is for `CaseResolver` to be handed
    its `workflow`/`golden` at construction time, via `Depends(...)`, the
    same way every other route dependency gets its collaborators — so it
    inherits whatever override chain FastAPI is already running.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from varuna_contracts.operator_case import OperatorCase
from varuna_domain.entities import Case


@dataclass
class ResolvedCase:
    """A case_id resolved against whichever store actually holds it.

    `case` is always the underlying domain `Case` (both `CaseWorkflow` and
    `GoldenCaseWorkflow` share the same `varuna_domain.entities.Case` type,
    so callers needing basic fields — status, created_at, metadata — don't
    need to care which store it came from).

    `workflow` is the OWNING workflow — the one whose `.praman` /
    `.event_spine` actually has this case's artifacts and events. Passing
    the wrong workflow to `build_operator_case` silently produces an
    operator view with zero artifacts, which is a second, quieter B1.

    `composed` is the already-built `OperatorCase`, when one exists (every
    replay case has one — it's the richest available view and must be
    preferred over rebuilding from `.metadata`, which the replay path
    doesn't populate the same way the legacy `/ingest` path does).
    """
    case: Case
    workflow: Any
    source: str  # "case_workflow" | "golden_case_engine"
    composed: Optional[OperatorCase] = None

    @property
    def has_operator_view(self) -> bool:
        """Whether `GET /v1/cases/{id}/operator-view` will actually succeed
        for this case.

        Went through two wrong definitions before this one:
          1. "a cache key happens to exist" (the original B1 bug — keyed by
             fixture name, not case_id, so it disagreed with reality).
          2. "a composed OperatorCase already exists" (`composed is not
             None`) — this session's first fix, and ALSO wrong: it made
             `list_all()` report `has_operator_view: false` for perfectly
             normal legacy `CaseWorkflow` cases (created via `POST
             /v1/cases`, never composed through the replay path), even
             though `get_operator_view()` builds a fresh `OperatorCase` for
             any resolvable case via `build_operator_case()` and always
             succeeds. A `false` that then 200s is the same class of lie as
             a `true` that 404s.

        The route's actual contract is simple: any case this resolver can
        find, it can produce a view for (composed when one exists, built
        fresh otherwise). So `has_operator_view` is just "this case
        resolves" — which is also why the field is redundant with mere
        presence in `list_all()`'s output; it's kept because a caller
        checking one boolean is clearer than checking for row presence."""
        return True


def _composed_by_case_id() -> dict[str, OperatorCase]:
    """`_COMPOSED_CACHE` is keyed by fixture_name; every value carries the
    real `case_id` (`REPLAY-{fixture_name}`) as an attribute. Re-key here,
    once, rather than asking every caller to know the fixture-name
    convention."""
    from apps.api.routers.replay import _COMPOSED_CACHE
    return {
        getattr(oc, "case_id", None): oc
        for oc in _COMPOSED_CACHE.values()
        if getattr(oc, "case_id", None)
    }


class CaseResolver:
    """Bound to a specific `workflow`/`golden` pair by
    `apps.api.dependencies.get_case_resolver`, which resolves both through
    FastAPI's own `Depends(...)` chain — so this class never has to guess
    which repos are live for the current request/test."""

    def __init__(self, workflow: Any, golden: Any) -> None:
        self._workflow = workflow
        self._golden = golden

    def resolve(self, case_id: str) -> Optional[ResolvedCase]:
        """Try, in order: legacy `CaseWorkflow` -> `GoldenCaseWorkflow`,
        attaching a composed `OperatorCase` from the replay cache when one
        exists for either. A replay case that HAS been composed is served
        with that richer product attached rather than rebuilt from
        `.metadata`, which the replay path doesn't populate the way the
        legacy `/ingest` path does."""
        composed_map = _composed_by_case_id()

        case = self._workflow.cases.get(case_id)
        if case is not None:
            return ResolvedCase(
                case=case, workflow=self._workflow, source="case_workflow",
                composed=composed_map.get(case_id),
            )

        golden_case = self._golden.cases.get(case_id)
        if golden_case is not None:
            return ResolvedCase(
                case=golden_case, workflow=self._golden, source="golden_case_engine",
                composed=composed_map.get(case_id),
            )

        return None

    def list_all(self) -> list[ResolvedCase]:
        """Every case either workflow knows about, deduplicated by case_id —
        exposed here so the contract test (list agrees with detail) can
        exercise the identical resolution logic the detail routes use, not
        a re-implementation of it."""
        composed_map = _composed_by_case_id()

        rows: dict[str, ResolvedCase] = {}
        for c in self._workflow.cases.list_all():
            rows[c.case_id] = ResolvedCase(
                case=c, workflow=self._workflow, source="case_workflow",
                composed=composed_map.get(c.case_id),
            )
        for c in self._golden.cases.list_all():
            rows[c.case_id] = ResolvedCase(
                case=c, workflow=self._golden, source="golden_case_engine",
                composed=composed_map.get(c.case_id),
            )

        return sorted(rows.values(), key=lambda r: str(r.case.created_at), reverse=True)
