"""
VARUNA GRID — canonical workflow guard (Phase: CANONICAL CASE WORKFLOW LOCK).

`varuna_domain.golden_case_engine.GoldenCaseWorkflow` is the canonical
product orchestration path. `varuna_domain.case_workflow.CaseWorkflow` is the
older, still-present orchestrator kept for compatibility — see
`docs/product/CANONICAL_WORKFLOW_POLICY.md` for the full rationale and the
classification of every caller enumerated below.

This test is the enforcement mechanism: it scans the repository for every
site that imports or instantiates `CaseWorkflow`, and fails if that set is
not EXACTLY the reviewed, classified allowlist below. It does not fail
because a caller exists — every current caller is legitimate and classified —
it fails when an *unreviewed* one appears, which is the only way "don't
accidentally bypass GoldenCaseWorkflow" can be enforced by CI rather than by
hoping someone remembers.

TO ADD A NEW CALLER: first read `docs/product/CANONICAL_WORKFLOW_POLICY.md`
and confirm `GoldenCaseWorkflow` genuinely cannot be used instead. If it
truly cannot, add the file to `_ALLOWED_CASEWORKFLOW_CALLERS` below with its
classification and a one-line reason, and add the same entry to the policy
doc's caller table. Do not add an entry just to make this test pass.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every file in this repository (relative to REPO_ROOT, forward slashes) that
# is permitted to import or instantiate `varuna_domain.case_workflow.CaseWorkflow`.
# Reviewed 2026-09-02 against a full repo-wide grep of `CaseWorkflow(` and
# `from varuna_domain.case_workflow import`. Each entry states WHY it is not
# on GoldenCaseWorkflow.
_ALLOWED_CASEWORKFLOW_CALLERS: dict[str, str] = {
    # --- Production / API: CaseWorkflow is genuinely the live orchestrator
    # for these routes today. Not migrated in this task (see policy doc
    # "what was intentionally not changed") because operator_case_view.py is
    # actively owned by concurrent work and a migration is a larger,
    # response-schema-affecting change than this lock task's scope.
    "apps/api/dependencies.py": "PRODUCTION: DI provider (get_workflow) backing every case route",
    "apps/api/operator_case_view.py": "PRODUCTION: build_operator_case(case, workflow: CaseWorkflow) — typed against CaseWorkflow",
    "apps/api/routers/cases.py": "PRODUCTION: all case-mutation endpoints depend on CaseWorkflow via get_workflow",
    "apps/api/routers/events.py": "PRODUCTION: case event listing depends on CaseWorkflow via get_workflow",

    # --- Scripts: legacy demo, and one "adapter-only" pattern (see policy
    # doc) where CaseWorkflow is used purely to satisfy build_operator_case's
    # signature, never for .ingest()/.reconstruct()/.attribute() orchestration.
    "scripts/demo_case_0001.py": "LEGACY: demo of the original CaseWorkflow vertical slice, predates GoldenCaseWorkflow",
    "scripts/mc20_track4_e2e.py": "COMPATIBILITY (adapter-only): drives RealE2EPipeline directly, then wraps the result in a throwaway CaseWorkflow solely to call build_operator_case() — never calls .ingest/.reconstruct/.attribute",

    # --- Tests: compatibility/regression tests for the legacy path, plus one
    # test mirroring the same adapter-only script pattern above.
    "tests/contract/test_operator_case.py": "COMPATIBILITY: exercises build_operator_case()'s CaseWorkflow-typed contract directly",
    "tests/integration/test_case_0001.py": "LEGACY/COMPATIBILITY: regression test of the original CaseWorkflow vertical slice",
    "tests/integration/test_e2e_persistence.py": "LEGACY/COMPATIBILITY: persistence regression test written against CaseWorkflow",
    "tests/integration/test_track4_mc20_e2e.py": "COMPATIBILITY (adapter-only): mirrors scripts/mc20_track4_e2e.py's pattern in a test fixture",
    "tests/regression/test_golden_cases.py": "LEGACY/COMPATIBILITY: software regression fixtures (CASE-0001 etc.) predating GoldenCaseWorkflow; 'golden' in the name refers to the fixtures, not the GoldenCaseWorkflow class",
}

_IMPORT_PATTERN = re.compile(
    r"from\s+varuna_domain\.case_workflow\s+import|"
    r"import\s+varuna_domain\.case_workflow"
)
# Negative lookbehind so "GoldenCaseWorkflow(" does not match — the substring
# "CaseWorkflow(" appears inside it, but that is the CANONICAL class.
_INSTANTIATION_PATTERN = re.compile(r"(?<!Golden)\bCaseWorkflow\(")

# This test file itself contains the literal strings "CaseWorkflow(" and
# "from varuna_domain.case_workflow import" inside documentation/allowlist
# text and the sanity-check test — it does not itself call the legacy
# orchestrator, so it is excluded from the scan the same way the defining
# module is.
_SELF = "tests/contract/test_canonical_workflow_guard.py"

# Directories scanned. Excludes the legacy `src/` tree (explicitly
# non-canonical, not part of the live app per repo-wide convention),
# `.venv`, and anything under `__pycache__`.
_SCAN_ROOTS = ["apps", "packages", "scripts", "tests"]

# The module that DEFINES CaseWorkflow is naturally exempt from being its own caller.
_SELF_DEFINITION = "packages/varuna_domain/case_workflow.py"
# golden_case_engine.py does not import CaseWorkflow (it wraps RealE2EPipeline
# directly, per docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md) but is
# listed here defensively so a future accidental import there is caught, not silently allowed.


def _find_case_workflow_references() -> set[str]:
    found: set[str] = set()
    for root_name in _SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in (_SELF_DEFINITION, _SELF):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _IMPORT_PATTERN.search(text) or _INSTANTIATION_PATTERN.search(text):
                found.add(rel)
    return found


def test_no_unreviewed_caseworkflow_callers():
    """
    Fails if any file references `CaseWorkflow` that is not in the reviewed
    allowlist above. This is the guard against a NEW production caller
    accidentally being wired to the legacy orchestrator instead of
    `GoldenCaseWorkflow`.
    """
    found = _find_case_workflow_references()
    allowed = set(_ALLOWED_CASEWORKFLOW_CALLERS.keys())

    unreviewed = found - allowed
    assert not unreviewed, (
        "Found file(s) referencing CaseWorkflow that are NOT in the reviewed "
        f"allowlist in this test: {sorted(unreviewed)}. "
        "Read docs/product/CANONICAL_WORKFLOW_POLICY.md — new product code "
        "must use GoldenCaseWorkflow. If this caller is a genuine, reviewed "
        "exception, add it to _ALLOWED_CASEWORKFLOW_CALLERS with a "
        "classification and reason, and add the same row to the policy doc."
    )


def test_allowlist_has_no_stale_entries():
    """
    The inverse check: fails if the allowlist names a file that no longer
    references CaseWorkflow (e.g. after a future migration), so the
    allowlist itself cannot silently drift out of date in the other
    direction.
    """
    found = _find_case_workflow_references()
    allowed = set(_ALLOWED_CASEWORKFLOW_CALLERS.keys())

    stale = allowed - found
    assert not stale, (
        f"Allowlist entries no longer reference CaseWorkflow: {sorted(stale)}. "
        "Remove them from _ALLOWED_CASEWORKFLOW_CALLERS (and the policy doc's "
        "caller table) now that they've been migrated to GoldenCaseWorkflow."
    )


def test_golden_case_workflow_is_importable_and_distinct():
    """Sanity check that the canonical path actually exists and is not, by
    some refactor, the same object as the legacy one."""
    from varuna_domain.case_workflow import CaseWorkflow
    from varuna_domain.golden_case_engine import GoldenCaseWorkflow

    assert GoldenCaseWorkflow is not CaseWorkflow
    assert not issubclass(GoldenCaseWorkflow, CaseWorkflow)
