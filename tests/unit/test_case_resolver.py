"""Unit coverage for `apps.api.case_resolver.CaseResolver` — the single
resolution path every case-scoped route and the case list now share
(Phase 1, B1 fix).

Built the same way `apps.api.dependencies.get_case_resolver` builds it —
from the process's real `get_workflow()`/`get_golden_case_workflow()` —
rather than re-deriving a workflow independently, which is exactly the
mistake `case_resolver.py`'s own module docstring records as rejected.
"""
from apps.api.case_resolver import CaseResolver
from apps.api.dependencies import (
    get_artifact_repo, get_case_repo, get_event_repo, get_golden_case_workflow,
    get_object_store, get_workflow,
)


def _resolver() -> CaseResolver:
    workflow = get_workflow(
        get_case_repo(), get_artifact_repo(), get_event_repo(), get_object_store(),
    )
    return CaseResolver(workflow=workflow, golden=get_golden_case_workflow())


def _warm_a_replay_case() -> str:
    """Compose at least one replay case via the real route path (the
    resolver's composed-cache lookup only finds a case once its fixture has
    actually been requested through `/v1/replay/{name}`)."""
    from fastapi.testclient import TestClient
    from apps.api.main import app

    client = TestClient(app)
    fixtures = client.get("/v1/replay/fixtures").json()["fixtures"]
    name = fixtures[0]
    client.get(f"/v1/replay/{name}")
    return f"REPLAY-{name}"


def test_resolve_returns_none_for_unknown_case():
    assert _resolver().resolve("NO-SUCH-CASE-ID") is None


def test_resolve_finds_a_composed_replay_case():
    case_id = _warm_a_replay_case()
    resolved = _resolver().resolve(case_id)
    assert resolved is not None
    assert resolved.case.case_id == case_id
    assert resolved.has_operator_view is True
    assert resolved.composed is not None
    assert resolved.composed.case_id == case_id


def test_list_all_agrees_with_resolve_for_every_case():
    """The exact invariant B1 violated: every case `list_all()` reports must
    be independently resolvable via `resolve()`, and their `has_operator_view`
    must agree."""
    _warm_a_replay_case()
    resolver = _resolver()
    for r in resolver.list_all():
        resolved = resolver.resolve(r.case.case_id)
        assert resolved is not None, f"{r.case.case_id} listed but not resolvable"
        assert resolved.has_operator_view == r.has_operator_view, r.case.case_id
