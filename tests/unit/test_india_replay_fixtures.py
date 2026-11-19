"""Phase 5/6 — curated Indian Ocean incident replay fixtures.

These are illustrative reconstructions of real, documented events (see each
scenario's `source_note` in packages/varuna_domain/replay_fixtures.py),
NOT live data and NOT a news-headline feed (explicit product decision).
Mirrors tests/unit/test_replay_fixtures.py's conventions for the original
six MC20-anchored fixtures, which this file does not touch or duplicate.
"""
from __future__ import annotations

import json

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_domain.entities import CaseStatus
from varuna_domain.golden_case_engine import derive_case_status
from varuna_domain.replay_fixtures import (
    ALL_FIXTURE_NAMES, FIXTURE_NAMES, INDIA_FIXTURE_NAMES, _INDIA_SCENARIOS,
    build_replay_run,
)


def test_india_fixtures_are_a_distinct_nonoverlapping_set():
    assert set(INDIA_FIXTURE_NAMES).isdisjoint(set(FIXTURE_NAMES))
    assert set(ALL_FIXTURE_NAMES) == set(FIXTURE_NAMES) | set(INDIA_FIXTURE_NAMES)
    assert len(INDIA_FIXTURE_NAMES) == 5


@pytest.mark.parametrize("name", INDIA_FIXTURE_NAMES)
def test_builds_without_error_and_completes(name):
    run = build_replay_run(name)
    assert run.finished_at is not None
    assert len(run.stages) == 10  # forcing..alerts, same 10 stages as CASE-VALID


@pytest.mark.parametrize("name", INDIA_FIXTURE_NAMES)
def test_reaches_complete_terminal_status(name):
    """Every India fixture models a real spill response that reached a
    decision — none are OOD/UNAVAILABLE/BLOCKED scenarios (those remain the
    original six's job)."""
    run = build_replay_run(name)
    status, _reason = derive_case_status(run)
    assert status == CaseStatus.COMPLETE


@pytest.mark.parametrize("name", INDIA_FIXTURE_NAMES)
def test_every_stage_is_simulated_never_real(name):
    """Illustrative reconstructions must never claim to be live measurements
    — the same honesty rule the original six fixtures enforce."""
    run = build_replay_run(name)
    for stage_name, result in run.stages.items():
        mode = result.evidence_mode
        mode_val = mode.value if hasattr(mode, "value") else mode
        assert mode_val != EvidenceMode.REAL.value, (
            f"{name}.{stage_name} claims REAL evidence — must be SIMULATED"
        )


@pytest.mark.parametrize("name", INDIA_FIXTURE_NAMES)
def test_json_serializable(name):
    run = build_replay_run(name)
    json.dumps(run.to_dict())


@pytest.mark.parametrize("name", INDIA_FIXTURE_NAMES)
def test_determinism_stable_across_two_builds(name):
    """Same convention and same excluded fields as
    test_replay_fixtures.py::test_deterministic_modulo_run_id_and_timestamps
    for the original six — run_id/timestamps/total_seconds/runtime_seconds
    are real wall-clock measurements, not fixture constants, so they
    legitimately vary between two builds a few microseconds apart."""
    run1 = build_replay_run(name, case_id=name)
    run2 = build_replay_run(name, case_id=name)
    d1, d2 = run1.to_dict(), run2.to_dict()
    for d in (d1, d2):
        for key in ("run_id", "started_at", "finished_at", "total_seconds"):
            d.pop(key, None)
        for stage in d["stages"].values():
            stage.pop("runtime_seconds", None)
    assert d1 == d2


@pytest.mark.parametrize("name", INDIA_FIXTURE_NAMES)
def test_geometry_is_within_the_indian_ocean_region_not_gulf_of_mexico(name):
    """Regression guard against accidentally reusing the MC20 anchor —
    every India fixture must have real Indian-Ocean-region coordinates."""
    scn = _INDIA_SCENARIOS[name]
    assert 0 <= scn.anchor.lon <= 100, f"{name} longitude {scn.anchor.lon} is not Indian-Ocean-region"
    assert -10 <= scn.anchor.lat <= 30, f"{name} latitude {scn.anchor.lat} is not Indian-Ocean-region"


def test_platform_source_scenario_has_no_vessel_candidate_identity():
    """IND-CASE-05 is deliberately a platform-sourced (not vessel-collision)
    scenario — its vessel fields must stay honest placeholders, not a
    fabricated identity."""
    scn = _INDIA_SCENARIOS["IND-CASE-05"]
    assert scn.vessel_mmsi == "000000000"
    assert "UNKNOWN" in scn.vessel_name


def test_each_scenario_documents_its_real_world_basis():
    for name, scn in _INDIA_SCENARIOS.items():
        assert scn.source_note, f"{name} must document what real event it models"
        assert len(scn.source_note) > 40, f"{name}'s source_note is too thin to be a real citation"


def test_ind_case_01_and_02_use_documented_real_vessel_identities():
    """BW Maple (2017 Chennai) and MSC Chitra (2010 Mumbai) are the two
    scenarios whose vessel identity is public record — verify their real
    names appear."""
    assert _INDIA_SCENARIOS["IND-CASE-01"].vessel_name == "BW MAPLE"
    assert _INDIA_SCENARIOS["IND-CASE-02"].vessel_name == "MSC CHITRA"
    assert _INDIA_SCENARIOS["IND-CASE-03"].vessel_name == "X-PRESS PEARL"
    assert _INDIA_SCENARIOS["IND-CASE-04"].vessel_name == "NEW DIAMOND"
