"""
Contract tests for the locked architectural invariants.

If any test here fails, an architectural rule has been broken — not a unit bug.
Fix the caller, or write an ADR. Do not relax these assertions.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from varuna_contracts import (
    CaseLifecycle,
    CaseStateVector,
    EvidenceEnvelope,
    EvidenceMode,
    EvidenceState,
    InvestigationState,
    MissionRecord,
    MissionState,
    OutcomeState,
    ResponseState,
    TrustState,
    ValidityState,
    check_case_invariants,
    is_legal_mission_transition,
)
from varuna_contracts.evidence import DegradationState, Provenance

pytestmark = pytest.mark.contract


def _env(**kw) -> EvidenceEnvelope:
    kw.setdefault("artifact_id", "a")
    kw.setdefault("produced_by", "test")
    kw.setdefault("provenance", Provenance(source_id="test"))
    kw.setdefault("mode", EvidenceMode.SIMULATED)
    return EvidenceEnvelope(**kw)


# ───────────────── Bounded Evidence Influence ─────────────────

@pytest.mark.parametrize(
    "trust,ceiling",
    [(TrustState.TRUSTED, 1.0), (TrustState.DEGRADED, 0.6),
     (TrustState.CONFLICTED, 0.3), (TrustState.QUARANTINED, 0.0)],
)
def test_influence_ceiling_enforced(trust, ceiling):
    """Above the trust ceiling must be rejected — by the custom validator, or by
    the field bound when the ceiling is already 1.0. Both are correct refusals."""
    _env(trust=trust, influence_weight=ceiling)  # at the ceiling is legal
    with pytest.raises(ValueError):
        _env(trust=trust, influence_weight=ceiling + 0.01)


def test_influence_ceiling_cites_the_architectural_rule():
    with pytest.raises(ValueError, match="Bounded Evidence Influence"):
        _env(trust=TrustState.DEGRADED, influence_weight=0.9)


def test_quarantined_source_has_zero_influence_and_is_not_actionable():
    e = _env(trust=TrustState.QUARANTINED, influence_weight=0.0)
    assert e.influence_weight == 0.0
    assert not e.is_actionable


# ───────────────── Uncertainty must propagate ─────────────────

@given(
    parent=st.sampled_from(list(TrustState)),
    other=st.sampled_from(list(TrustState)),
)
def test_derive_never_upgrades_trust(parent, other):
    """A subsystem cannot launder a DEGRADED input into a TRUSTED output."""
    a = _env(artifact_id="a", trust=parent, influence_weight=parent.max_influence)
    b = _env(artifact_id="b", trust=other, influence_weight=other.max_influence)
    out = a.derive(artifact_id="c", produced_by="netra", also_from=[b])
    assert out.trust.rank >= max(parent.rank, other.rank)
    assert out.influence_weight <= min(a.influence_weight, b.influence_weight) + 1e-9


@given(v=st.sampled_from(list(ValidityState)), d=st.sampled_from(list(DegradationState)))
def test_derive_never_upgrades_validity_or_degradation(v, d):
    a = _env(validity_state=v, degradation_state=d)
    out = a.derive(artifact_id="c", produced_by="nyaya")
    assert out.validity_state.rank >= v.rank
    assert out.degradation_state.rank >= d.rank


def test_derive_merges_lineage_and_flags():
    a = _env(artifact_id="a", provenance=Provenance(source_id="cmems",
                                                    raw_artifact_refs=["raw/cmems.nc"]))
    b = _env(artifact_id="b", provenance=Provenance(source_id="era5",
                                                    raw_artifact_refs=["raw/era5.nc"]))
    out = a.derive(artifact_id="phi", produced_by="prativartan", also_from=[b])
    assert set(out.parent_artifact_ids) == {"a", "b"}
    assert out.provenance.raw_artifact_refs == ["raw/cmems.nc", "raw/era5.nc"]


def test_content_hash_is_stable_and_order_independent():
    a = _env().with_content_hash({"x": 1, "y": 2})
    b = _env().with_content_hash({"y": 2, "x": 1})
    assert a.content_hash == b.content_hash and a.content_hash is not None


# ───────────────── Validity gates operational action ─────────────────

@pytest.mark.parametrize(
    "state,allowed",
    [(ValidityState.VALID, True), (ValidityState.DEGRADED, True),
     (ValidityState.RESTRICTED, False), (ValidityState.INCONCLUSIVE, False)],
)
def test_only_valid_and_degraded_reach_the_action_gateway(state, allowed):
    assert _env(validity_state=state).is_actionable is allowed


# ───────────────── Case invariants ─────────────────

def test_asset_cannot_be_committed_on_inconclusive_outcome():
    s = CaseStateVector(
        investigation=InvestigationState.ATTRIBUTED,
        outcome=OutcomeState.INCONCLUSIVE,
        response=ResponseState.EN_ROUTE,
    )
    assert any("non-dispatchable" in v for v in check_case_invariants(s))


def test_outcome_cannot_precede_attribution():
    s = CaseStateVector(investigation=InvestigationState.TRIAGED,
                        outcome=OutcomeState.STRONG_LEAD)
    assert any("before investigation" in v for v in check_case_invariants(s))


def test_case_cannot_close_without_evidence():
    s = CaseStateVector(lifecycle=CaseLifecycle.CLOSED, evidence=EvidenceState.NONE)
    assert any("PRAMAN" in v for v in check_case_invariants(s))


def test_nominal_flow_has_no_violations():
    s = CaseStateVector(
        investigation=InvestigationState.ATTRIBUTED,
        outcome=OutcomeState.STRONG_LEAD,
        response=ResponseState.EN_ROUTE,
        evidence=EvidenceState.PARTIAL,
    )
    assert check_case_invariants(s) == []


# ───────────────── Mission FSM ─────────────────

def test_assignment_requires_human_authorization():
    m = MissionRecord(mission_id="m", case_id="c", asset_id="dornier-1")
    m.transition(MissionState.RESERVED)
    with pytest.raises(ValueError, match="authorization gate"):
        m.transition(MissionState.ASSIGNED)
    m.human_approved_by = "officer-7"
    m.transition(MissionState.ASSIGNED)
    assert m.state is MissionState.ASSIGNED


def test_illegal_transitions_are_rejected():
    m = MissionRecord(mission_id="m", case_id="c", asset_id="a")
    with pytest.raises(ValueError, match="illegal mission transition"):
        m.transition(MissionState.ON_STATION)


def test_closed_is_terminal():
    assert not any(is_legal_mission_transition(MissionState.CLOSED, d)
                   for d in MissionState)


def test_state_history_is_recorded_for_audit():
    m = MissionRecord(mission_id="m", case_id="c", asset_id="a",
                      human_approved_by="officer-1")
    m.transition(MissionState.RESERVED)
    m.transition(MissionState.ASSIGNED)
    assert [s for s, _ in m.state_history] == ["reserved", "assigned"]
