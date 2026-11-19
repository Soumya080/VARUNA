"""
Contract tests for EvidenceMode (ADR-0006).

If any test here fails, an architectural rule has been broken — not a unit
bug. Fix the caller, or write a new ADR. Do not relax these assertions.
"""
import ast
import inspect
from pathlib import Path

import pytest

from varuna_contracts.evidence import (
    DegradationState,
    EvidenceEnvelope,
    EvidenceMode,
    Provenance,
)

pytestmark = pytest.mark.contract


def _env(mode: EvidenceMode, **kw) -> EvidenceEnvelope:
    kw.setdefault("artifact_id", "a")
    kw.setdefault("produced_by", "test")
    kw.setdefault("provenance", Provenance(source_id="test"))
    return EvidenceEnvelope(mode=mode, **kw)


# ───────────────────────── mode is required ─────────────────────────

def test_mode_is_required():
    with pytest.raises(Exception):
        EvidenceEnvelope(
            artifact_id="a", produced_by="test",
            provenance=Provenance(source_id="test"),
        )  # no mode= -> must fail construction


def test_rank_orders_real_best_unavailable_worst():
    assert EvidenceMode.REAL.rank < EvidenceMode.SIMULATED.rank < EvidenceMode.UNAVAILABLE.rank


# ───────────────────────── derive() monotonicity matrix ─────────────────────────

@pytest.mark.parametrize(
    "a,b,expected",
    [
        (EvidenceMode.REAL, EvidenceMode.REAL, EvidenceMode.REAL),
        (EvidenceMode.REAL, EvidenceMode.SIMULATED, EvidenceMode.SIMULATED),
        (EvidenceMode.SIMULATED, EvidenceMode.REAL, EvidenceMode.SIMULATED),
        (EvidenceMode.SIMULATED, EvidenceMode.SIMULATED, EvidenceMode.SIMULATED),
        (EvidenceMode.REAL, EvidenceMode.UNAVAILABLE, EvidenceMode.UNAVAILABLE),
        (EvidenceMode.SIMULATED, EvidenceMode.UNAVAILABLE, EvidenceMode.UNAVAILABLE),
        (EvidenceMode.UNAVAILABLE, EvidenceMode.UNAVAILABLE, EvidenceMode.UNAVAILABLE),
        (EvidenceMode.UNAVAILABLE, EvidenceMode.REAL, EvidenceMode.UNAVAILABLE),
        (EvidenceMode.UNAVAILABLE, EvidenceMode.SIMULATED, EvidenceMode.UNAVAILABLE),
    ],
)
def test_derive_mode_matrix(a, b, expected):
    parent = _env(a)
    other = _env(b)
    derived = parent.derive(artifact_id="child", produced_by="test", also_from=[other])
    assert derived.mode is expected


def test_derive_with_no_also_from_preserves_parent_mode():
    for mode in EvidenceMode:
        parent = _env(mode)
        derived = parent.derive(artifact_id="child", produced_by="test")
        assert derived.mode is mode


def test_derive_with_three_inputs_takes_the_worst():
    a = _env(EvidenceMode.REAL)
    b = _env(EvidenceMode.REAL)
    c = _env(EvidenceMode.SIMULATED)
    derived = a.derive(artifact_id="child", produced_by="test", also_from=[b, c])
    assert derived.mode is EvidenceMode.SIMULATED


# ───────────────────────── structural impossibility of upgrading ─────────────────────────

def test_simulated_cannot_become_real_via_derive():
    """
    There is no parameter on derive() through which a caller could even
    attempt to set mode=REAL on a SIMULATED lineage — this is checked at
    the API level (no such kwarg exists) rather than only at the value
    level, so it is enforced whether or not a test remembers to check it.
    """
    sig = inspect.signature(EvidenceEnvelope.derive)
    assert "mode" not in sig.parameters, (
        "EvidenceEnvelope.derive() must not accept a `mode` override parameter — "
        "mode is derived (monotonic worst-of-inputs) only, never asserted by a caller"
    )

    simulated = _env(EvidenceMode.SIMULATED)
    derived = simulated.derive(artifact_id="child", produced_by="test")
    assert derived.mode is EvidenceMode.SIMULATED


def test_unavailable_cannot_become_real_via_derive():
    unavailable = _env(EvidenceMode.UNAVAILABLE)
    real_input = _env(EvidenceMode.REAL)
    derived = unavailable.derive(artifact_id="child", produced_by="test", also_from=[real_input])
    assert derived.mode is EvidenceMode.UNAVAILABLE


def test_unavailable_cannot_become_simulated_via_derive():
    unavailable = _env(EvidenceMode.UNAVAILABLE)
    simulated_input = _env(EvidenceMode.SIMULATED)
    derived = unavailable.derive(artifact_id="child", produced_by="test", also_from=[simulated_input])
    assert derived.mode is EvidenceMode.UNAVAILABLE


# ───────────────────────── cached replay cannot claim REAL ─────────────────────────

def test_cached_replay_cannot_claim_real():
    with pytest.raises(Exception):
        _env(EvidenceMode.REAL, degradation_state=DegradationState.CACHED_REPLAY)


def test_cached_replay_can_claim_simulated():
    env = _env(EvidenceMode.SIMULATED, degradation_state=DegradationState.CACHED_REPLAY)
    assert env.mode is EvidenceMode.SIMULATED
    assert env.degradation_state is DegradationState.CACHED_REPLAY


def test_cached_replay_can_claim_unavailable():
    env = _env(EvidenceMode.UNAVAILABLE, degradation_state=DegradationState.CACHED_REPLAY)
    assert env.mode is EvidenceMode.UNAVAILABLE


# ───────────────────────── configuration cannot upgrade provenance ─────────────────────────

def test_no_settings_or_config_reference_assigns_mode_real():
    """
    Static check over the actual source, not a convention documented in a
    comment: scan every `mode=` assignment/keyword-argument site in the
    contracts, prativartan, and nyaya packages, and fail if any right-hand
    side references `settings`, `config`, or `os.environ` — the only
    accepted origins for EvidenceMode.REAL are a real source adapter's
    `FetchResult.is_simulated=False`, or an explicit mock/synthetic
    provider constant. `config` objects that are NOT settings (e.g.
    PratiConfig, a plain parameter bag with no env/settings backing) are
    fine to reference elsewhere in the file; this check only inspects the
    actual value assigned to `mode=`.
    """
    scan_roots = [
        Path("packages/varuna_contracts"),
        Path("packages/varuna_prativartan"),
        Path("packages/varuna_nyaya"),
        Path("packages/varuna_source_adapters"),
    ]
    offending: list[str] = []

    for root in scan_roots:
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg == "mode":
                    src = ast.dump(node.value)
                    if any(bad in src for bad in ("settings", "os.environ", "getenv")):
                        offending.append(f"{py_file}:{node.value.lineno}: {src}")
                # Also catch `self.mode = ...` / `envelope.mode = ...` assignment form.
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and target.attr == "mode":
                            src = ast.dump(node.value)
                            if any(bad in src for bad in ("settings", "os.environ", "getenv")):
                                offending.append(f"{py_file}:{node.lineno}: {src}")

    assert offending == [], (
        "Found `mode=` assignment(s) sourced from settings/config/env — "
        "EvidenceMode must never be configuration-controlled:\n" + "\n".join(offending)
    )
