"""
CHHAYA v0.1 — source-hypothesis engine.

Asserts behaviour and honesty properties, not specific posterior values: the
declared likelihood ratios are expected to be tuned as the engine matures, and
a test that pins 0.866 would break on every legitimate re-weighting while
proving nothing about correctness.
"""
from __future__ import annotations

import pytest

from varuna_chhaya.hypothesis_engine import (
    GULF_OF_MEXICO_PRIORS, SourceHypothesisEngine,
)
from varuna_contracts.evidence import (
    EvidenceEnvelope, EvidenceMode, Provenance,
)
from varuna_contracts.source_hypothesis import HypothesisMethod, SourceClass

pytestmark = pytest.mark.unit


def _env(mode: EvidenceMode = EvidenceMode.REAL) -> EvidenceEnvelope:
    return EvidenceEnvelope(artifact_id="parent", produced_by="test",
                            provenance=Provenance(source_id="test"), mode=mode)


def _engine() -> SourceHypothesisEngine:
    return SourceHypothesisEngine()


def test_posteriors_are_a_probability_distribution():
    r = _engine().assess(case_id="C1", parent_envelope=_env(), detection_present=True,
                         elongation=4.0, nearest_vessel_km=3.0,
                         nearest_vessel_temporally_matched=True)
    assert sum(h.posterior for h in r.hypotheses) == pytest.approx(1.0)
    assert len({h.source_class for h in r.hypotheses}) == len(r.hypotheses)


def test_colocated_time_matched_vessel_favours_vessel_hypothesis():
    r = _engine().assess(case_id="C1", parent_envelope=_env(), detection_present=True,
                         elongation=5.0, nearest_vessel_km=2.0,
                         nearest_vessel_temporally_matched=True,
                         distance_to_shore_km=60.0)
    assert r.top.source_class is SourceClass.VESSEL_ASSOCIATED
    assert r.is_discriminating


def test_spatial_only_vessel_is_weaker_than_a_temporal_match():
    """
    Mirrors the AIS join's own rule that spatial candidacy is never promoted
    into temporal evidence — the same slick with an unmatched track must not
    score as confidently.
    """
    common = dict(case_id="C1", parent_envelope=_env(), detection_present=True,
                  elongation=5.0, nearest_vessel_km=2.0, distance_to_shore_km=60.0)
    matched = _engine().assess(**common, nearest_vessel_temporally_matched=True)
    spatial = _engine().assess(**common, nearest_vessel_temporally_matched=False)

    def vessel(r):
        return next(h.posterior for h in r.hypotheses
                    if h.source_class is SourceClass.VESSEL_ASSOCIATED)

    assert vessel(spatial) < vessel(matched)


def test_recurrence_in_a_seep_basin_favours_natural_seep():
    engine = SourceHypothesisEngine(priors=GULF_OF_MEXICO_PRIORS,
                                    region_note="Gulf of Mexico")
    r = engine.assess(case_id="C2", parent_envelope=_env(), detection_present=True,
                      elongation=1.2, nearest_vessel_km=40.0,
                      in_known_seep_basin=True, prior_cases_same_corridor=6,
                      distance_to_shore_km=80.0)
    assert r.top.source_class is SourceClass.NATURAL_SEEP


def test_no_detection_yields_honest_unknown_not_a_flat_spread():
    r = _engine().assess(case_id="C3", parent_envelope=_env(), detection_present=False)
    assert r.insufficient_evidence is True
    assert r.top.source_class is SourceClass.UNKNOWN
    assert r.top.posterior == pytest.approx(1.0)
    assert all(h.posterior == 0.0 for h in r.hypotheses
               if h.source_class is not SourceClass.UNKNOWN)


def test_missing_evidence_contributes_nothing_rather_than_a_default():
    """
    An unobserved quantity must never push a hypothesis. With no evidence at
    all beyond the detection existing, posteriors must equal the declared priors.
    """
    r = _engine().assess(case_id="C4", parent_envelope=_env(), detection_present=True)
    for h in r.hypotheses:
        assert h.posterior == pytest.approx(h.prior), h.source_class


def test_engine_never_claims_to_be_a_learned_model():
    r = _engine().assess(case_id="C5", parent_envelope=_env(), detection_present=True,
                         nearest_vessel_km=1.0, nearest_vessel_temporally_matched=True)
    assert r.method is HypothesisMethod.DECLARED_LIKELIHOOD_RATIO
    assert r.method is not HypothesisMethod.LEARNED_MODEL
    note = r.methodology_note.lower()
    assert "not a trained or learned model" in note
    assert "uncalibrated" in note


def test_factor_contributions_are_inspectable_and_attributed():
    r = _engine().assess(case_id="C6", parent_envelope=_env(), detection_present=True,
                         nearest_vessel_km=2.0, nearest_vessel_temporally_matched=True,
                         elongation=6.0)
    vessel = next(h for h in r.hypotheses
                  if h.source_class is SourceClass.VESSEL_ASSOCIATED)
    assert vessel.supporting, "a supported hypothesis must name its factors"
    for fc in vessel.supporting:
        assert fc.factor and fc.detail
        assert fc.log_likelihood_ratio > 0
    assert "Prior" in vessel.rationale


def test_absent_ais_is_flagged_as_an_assumption_not_a_measurement():
    """
    "No AIS" is not evidence of "no vessel" — a dark vessel produces no AIS
    either. The factor must be recorded as unmeasured so it is visibly weak.
    """
    r = _engine().assess(case_id="C7", parent_envelope=_env(), detection_present=True,
                         n_ais_tracks=0)
    vessel = next(h for h in r.hypotheses
                  if h.source_class is SourceClass.VESSEL_ASSOCIATED)
    factors = vessel.supporting + vessel.contradicting
    no_ais = [f for f in factors if f.factor == "no_ais_coverage"]
    assert no_ais and no_ais[0].measured is False
    assert "dark vessel" in no_ais[0].detail.lower()


def test_low_wind_widens_uncertainty_rather_than_choosing_a_source():
    """Low wind is a detection-quality caveat, not source evidence."""
    r = _engine().assess(case_id="C8", parent_envelope=_env(), detection_present=True,
                         wind_speed_ms=1.5)
    unknown = next(h for h in r.hypotheses if h.source_class is SourceClass.UNKNOWN)
    assert any(f.factor == "low_wind_lookalike_risk" for f in unknown.supporting)
    assert unknown.posterior > unknown.prior


def test_contradictions_increase_unknown_and_are_carried_through():
    r = _engine().assess(case_id="C9", parent_envelope=_env(), detection_present=True,
                         contradictions=["detection says oil, AIS says no vessel"])
    unknown = next(h for h in r.hypotheses if h.source_class is SourceClass.UNKNOWN)
    assert unknown.posterior > unknown.prior
    assert r.contradictions == ["detection says oil, AIS says no vessel"]


def test_evidence_mode_propagates_and_never_improves():
    r = _engine().assess(case_id="C10", parent_envelope=_env(EvidenceMode.SIMULATED),
                         detection_present=True, nearest_vessel_km=1.0,
                         nearest_vessel_temporally_matched=True)
    assert r.envelope.mode is EvidenceMode.SIMULATED


def test_single_factor_case_is_flagged_as_non_discriminating():
    r = _engine().assess(case_id="C11", parent_envelope=_env(), detection_present=True,
                         in_known_seep_basin=True)
    assert r.uncertainty_note is not None
    assert "one evidential factor" in r.uncertainty_note


def test_engine_is_deterministic():
    kw = dict(case_id="C12", parent_envelope=_env(), detection_present=True,
              elongation=3.5, nearest_vessel_km=4.0,
              nearest_vessel_temporally_matched=True, distance_to_shore_km=30.0)
    a = _engine().assess(**kw)
    b = _engine().assess(**kw)
    assert ([(h.source_class, h.posterior) for h in a.hypotheses]
            == [(h.source_class, h.posterior) for h in b.hypotheses])


def test_priors_that_do_not_sum_to_one_are_rejected():
    with pytest.raises(ValueError, match="sum to 1.0"):
        SourceHypothesisEngine(priors={SourceClass.VESSEL_ASSOCIATED: 0.5,
                                       SourceClass.UNKNOWN: 0.2})
