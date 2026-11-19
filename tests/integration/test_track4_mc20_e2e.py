"""
Track 4 - bounded MC20 integration tests over the real Event Gold.

Runs the pipeline ONCE per session at a deliberately tiny scale (20 particles,
4 ensemble members, 5 AIS tracks) and asserts the seams, not the science. No
GPU work, no NETRA inference, no production ensemble - safe to run while
training occupies the card.

Skipped entirely when `data/gold/events/mc20_v0_1` is absent, so a checkout
without the (gitignored) Gold corpus still has a green suite.
"""
from __future__ import annotations

# Schema imports before netCDF4 (Windows DLL interaction - see forcing.py).
from varuna_contracts.evidence import EvidenceMode  # isort: skip

import json
from pathlib import Path

import pytest

from varuna_integration.stage import StageStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"

pytestmark = pytest.mark.skipif(
    not (GOLD / "manifest.json").exists(),
    reason="MC20 Event Gold is not present in this checkout (gitignored corpus)",
)


def _event_acquisition_time(manifest) -> "datetime":
    """The event's real SAR acquisition time, from the Gold manifest."""
    from datetime import datetime, timezone

    return datetime.strptime(
        manifest["event_id"].split("_")[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def run():
    """One bounded pipeline run, shared by every test in this module."""
    from varuna_alerts.channels.console import ConsoleChannel
    from varuna_alerts.service import AlertService
    from varuna_contracts.schemas import BBox, GeoPoint
    from varuna_integration.netra_boundary import SimulatedSlickProvider
    from varuna_integration.netra_boundary import NetraDetectionBoundary
    from varuna_integration.pipeline import PipelineConfig, RealE2EPipeline
    from varuna_missions.repository import InMemoryMissionRepository
    from varuna_missions.service import MissionService

    manifest = json.loads((GOLD / "manifest.json").read_text(encoding="utf-8"))
    bb = manifest["modalities"]["sar"]["bbox"]
    clon = (bb["min_lon"] + bb["max_lon"]) / 2
    clat = (bb["min_lat"] + bb["max_lat"]) / 2
    provider = SimulatedSlickProvider(
        centroid=GeoPoint(lon=clon, lat=clat),
        bbox=BBox(min_lon=clon - 0.05, min_lat=clat - 0.05,
                  max_lon=clon + 0.05, max_lat=clat + 0.05),
        scene_id=manifest["event_id"],
        # The event's REAL acquisition time, not the `now()` default. A
        # placeholder dated today clamps to the forcing window edge and
        # advects against a current regime unrelated to the event - on MC20
        # that alone moves particle loss between 0% and 70%.
        observation_time=_event_acquisition_time(manifest),
    )
    boundary = NetraDetectionBoundary(
        provider, EvidenceMode.SIMULATED, source_id="test.simulated_placeholder")

    pipeline = RealE2EPipeline(
        PipelineConfig(gold_dir=GOLD, n_particles=20, n_ensemble=4,
                       max_ais_tracks=3, max_netra_tiles=2),
        netra=boundary,
        mission_service=MissionService(InMemoryMissionRepository()),
        alert_service=AlertService([ConsoleChannel()]),
    )
    return pipeline.run()


# ------------------------------- seam coverage -------------------------------

def test_every_stage_is_recorded(run):
    """No stage may be silently absent from the run record."""
    expected = {
        "forcing", "netra_detection", "ais_ingest", "phi_reconstruction",
        "attribution", "validity", "forecast", "decision", "mission", "alerts",
    }
    assert expected <= set(run.stages)


def test_no_stage_is_blocked(run):
    """A BLOCKED stage means a genuine integration break, not a science result."""
    blocked = {n: s.reason for n, s in run.stages.items()
               if s.status is StageStatus.BLOCKED}
    assert not blocked, f"integration break: {blocked}"


def test_every_non_produced_stage_states_why(run):
    for name, s in run.stages.items():
        if s.status is not StageStatus.PRODUCED:
            assert s.reason, f"stage {name} produced nothing without saying why"


# ------------------------------ forcing is real ------------------------------

def test_forcing_boundary_is_real(run):
    f = run.stages["forcing"]
    assert f.status is StageStatus.PRODUCED
    assert f.evidence_mode is EvidenceMode.REAL
    assert f.detail["era5_time_series_status"] == "sufficient"
    assert f.detail["cmems_time_series_status"] == "sufficient"
    assert f.detail["overlap_hours"] > 0


# -------------------------------- AIS is real --------------------------------

def test_ais_adapter_yields_real_evidence_mode(run):
    a = run.stages["ais_ingest"]
    assert a.status is StageStatus.PRODUCED
    assert a.evidence_mode is EvidenceMode.REAL, "real AIS on disk must read as REAL"
    assert a.detail["n_returned"] > 0


def test_only_temporally_matched_tracks_are_returned(run):
    """Spatial candidacy must not leak in as temporal evidence."""
    a = run.stages["ais_ingest"]
    assert set(a.detail["track_join_status"].values()) == {"temporally_matched"}


def test_spatial_and_temporal_counts_are_reported_separately(run):
    a = run.stages["ais_ingest"]
    assert a.detail["n_spatially_matched"] >= a.detail["n_temporally_matched"]
    assert a.detail["n_tracks_total"] >= a.detail["n_spatially_matched"]


# ------------------------------ wind diagnostic ------------------------------

def test_real_wind_speed_is_recorded_at_each_detection(run):
    """The low-wind look-alike condition must be observable to an operator."""
    d = run.stages["netra_detection"]
    if d.status is not StageStatus.PRODUCED:
        pytest.skip("no detection produced")
    wind = d.detail.get("wind_context")
    assert wind is not None, "detections must carry real wind context"
    assert wind["n_sampled"] > 0
    assert wind["low_wind_threshold_ms"] == 3.0
    for obs in wind["per_detection"]:
        # Either a real measured speed, or an explicit reason it is unavailable.
        assert obs.get("wind_speed_ms") is not None or obs.get("reason")


def test_wind_context_does_not_reclassify_any_detection(run):
    """It is a diagnostic. Look-alike discrimination is NETRA's call, not ours."""
    d = run.stages["netra_detection"]
    if d.status is not StageStatus.PRODUCED:
        pytest.skip("no detection produced")
    classes_before = {det.classification for det in d.value}
    assert "no detection was reclassified" in d.detail["wind_context"]["note"].lower()
    assert {det.classification for det in d.value} == classes_before


# --------------------------- Phi / NYAYA / Validity ---------------------------

def test_phi_is_produced_with_honest_diagnostics(run):
    p = run.stages["phi_reconstruction"]
    assert p.status is StageStatus.PRODUCED
    # A 20-particle/4-member ensemble genuinely does not converge. Asserting it
    # DOES would be asserting a fabrication.
    assert p.detail["convergence_flag"] in ("not_converged", "converged", "marginal")
    assert p.detail["n_ensemble_completed"] == p.detail["n_ensemble_requested"]


def test_phi_sensitivity_is_none_unless_the_sweep_ran(run):
    """ADR-0007: the cheap path leaves sensitivity unset. It must stay unset,
    not be filled with a plausible number."""
    assert run.stages["phi_reconstruction"].detail["sensitivity"] is None


def test_attribution_runs_against_real_tracks(run):
    a = run.stages["attribution"]
    assert a.status is StageStatus.PRODUCED
    assert a.detail["n_candidates"] > 0
    assert a.detail["decision_state"]


def test_validity_gate_reports_real_reason_codes(run):
    v = run.stages["validity"]
    assert v.status is StageStatus.PRODUCED, "a restrictive gate still RAN"
    if not v.detail["allows_operational_action"]:
        assert v.detail["failing_checks"] or v.detail["blocking_reasons"], \
            "a gate that denies action must name at least one failing check"


def test_simulated_lineage_is_flagged_to_the_officer(run):
    """The caveat list is what an operator reads. A simulated case must say so."""
    caveats = " ".join(run.stages["validity"].detail["officer_visible_caveats"]).lower()
    assert "simulated" in caveats


# ------------------------------- fail-closed -------------------------------

def test_restricted_gate_suppresses_tasking(run):
    """ABHIYAN must not plan against a gate that denies operational action."""
    v, d = run.stages["validity"], run.stages["decision"]
    if not v.detail["allows_operational_action"]:
        assert d.status is not StageStatus.PRODUCED
        assert "NO_TASKING" in d.reason


def test_no_tasking_means_no_mission(run):
    d, m = run.stages["decision"], run.stages["mission"]
    if d.status is not StageStatus.PRODUCED:
        assert m.status is StageStatus.NOT_YET_PRODUCED
        assert "NO_TASKING_TO_PROPOSE" in m.reason


def test_no_mission_is_ever_auto_dispatched(run):
    """Phase 10: missions may be proposed, never authorized, by the pipeline."""
    m = run.stages["mission"]
    if m.status is StageStatus.PRODUCED:
        assert all(a is None for a in m.detail["human_approved"]), \
            "the pipeline must never supply a human approver"
        assert "assigned" not in [s.lower() for s in m.detail["states"]]


def test_alerts_never_claim_undelivered_delivery(run):
    a = run.stages["alerts"]
    if a.status is StageStatus.PRODUCED:
        if a.detail["n_actually_delivered"] == 0:
            assert "delivered" not in a.detail["delivery_claim"].lower() or \
                   "no " in a.detail["delivery_claim"].lower()


# ---------------------- Phase 14: evidence-mode propagation ----------------------

def test_simulated_detection_poisons_the_whole_downstream_lineage(run):
    """REAL forcing + REAL AIS + SIMULATED detection must NOT yield REAL."""
    assert run.stages["netra_detection"].evidence_mode is EvidenceMode.SIMULATED
    assert run.stages["forcing"].evidence_mode is EvidenceMode.REAL
    assert run.stages["ais_ingest"].evidence_mode is EvidenceMode.REAL
    for stage in ("phi_reconstruction", "attribution", "validity"):
        assert run.stages[stage].evidence_mode is EvidenceMode.SIMULATED, \
            f"{stage} must not be promoted back to REAL"
    assert run.evidence_mode is EvidenceMode.SIMULATED


def test_run_mode_is_never_better_than_its_worst_stage(run):
    order = {EvidenceMode.REAL: 0, EvidenceMode.SIMULATED: 1, EvidenceMode.UNAVAILABLE: 2}
    worst = max((order[s.evidence_mode] for s in run.stages.values()
                 if s.evidence_mode is not None), default=0)
    assert order[run.evidence_mode] == worst


# ---------------------- Phase 12: OperatorCase serialization ----------------------

@pytest.fixture(scope="module")
def operator_case(run):
    from apps.api.operator_case_view import build_operator_case
    from varuna_domain.case_workflow import CaseWorkflow
    from varuna_domain.entities import Case
    from varuna_domain.repositories import (
        InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
    )
    from varuna_integration.case_bridge import apply_run_to_case

    workflow = CaseWorkflow(InMemoryCaseRepository(), InMemoryArtifactRepository(),
                            InMemoryEventStore())
    case = Case(run.case_id)
    apply_run_to_case(case, run)
    workflow.cases.save(case)
    return build_operator_case(case, workflow)


def test_operator_case_serializes(operator_case):
    payload = json.loads(operator_case.model_dump_json())
    assert payload["case_id"]
    for section in ("observation", "detection", "origin", "ais", "attribution",
                    "validity", "forecast", "decision", "mission", "alerts"):
        assert section in payload
        assert payload[section]["status"]


def test_detection_section_reports_simulated_not_real(operator_case):
    """The regression this fixes: the projection used to hardcode REAL for any
    detection it found, which would relabel a placeholder as real evidence."""
    assert operator_case.detection.evidence_mode is EvidenceMode.SIMULATED


def test_every_empty_section_carries_a_reason(operator_case):
    for name in ("observation", "detection", "origin", "ais", "attribution",
                 "validity", "forecast", "decision", "mission", "alerts"):
        sec = getattr(operator_case, name)
        if sec.value is None:
            assert sec.reason, f"section {name} is empty with no reason given"


def test_operator_case_reports_real_ais_candidates(operator_case):
    assert operator_case.ais.value, "real AIS tracks must reach the operator view"
    assert all(c.mmsi for c in operator_case.ais.value)


def test_no_fabricated_dashboard_numbers(operator_case):
    """Guards against the screenshot values ever being hardcoded."""
    payload = operator_case.model_dump_json()
    for forbidden in ('"confidence": 0.87', '"attribution": 0.642', '64.2'):
        assert forbidden not in payload


# ------------------- particle-count honesty (behavioural) -------------------

def _scientific_pipeline(n_particles: int):
    """A SCIENTIFIC-classed pipeline over the same bounded simulated detection."""
    from varuna_alerts.channels.console import ConsoleChannel
    from varuna_alerts.service import AlertService
    from varuna_contracts.schemas import BBox, GeoPoint
    from varuna_integration.netra_boundary import (
        NetraDetectionBoundary, SimulatedSlickProvider)
    from varuna_integration.pipeline import PipelineConfig, RealE2EPipeline
    from varuna_missions.repository import InMemoryMissionRepository
    from varuna_missions.service import MissionService

    manifest = json.loads((GOLD / "manifest.json").read_text(encoding="utf-8"))
    bb = manifest["modalities"]["sar"]["bbox"]
    clon = (bb["min_lon"] + bb["max_lon"]) / 2
    clat = (bb["min_lat"] + bb["max_lat"]) / 2
    provider = SimulatedSlickProvider(
        centroid=GeoPoint(lon=clon, lat=clat),
        bbox=BBox(min_lon=clon - 0.05, min_lat=clat - 0.05,
                  max_lon=clon + 0.05, max_lat=clat + 0.05),
        scene_id=manifest["event_id"],
        # The event's REAL acquisition time, not the `now()` default. A
        # placeholder dated today clamps to the forcing window edge and
        # advects against a current regime unrelated to the event - on MC20
        # that alone moves particle loss between 0% and 70%.
        observation_time=_event_acquisition_time(manifest),
    )
    return RealE2EPipeline(
        PipelineConfig(gold_dir=GOLD, n_particles=n_particles, n_ensemble=4,
                       max_ais_tracks=3, max_netra_tiles=2,
                       run_class="SCIENTIFIC"),
        netra=NetraDetectionBoundary(
            provider, EvidenceMode.SIMULATED, source_id="test.simulated_placeholder"),
        mission_service=MissionService(InMemoryMissionRepository()),
        alert_service=AlertService([ConsoleChannel()]),
    )


def test_under_resolved_scientific_run_blocks_instead_of_advecting_fewer(monkeypatch):
    """With too few observation points, a SCIENTIFIC run must block rather than
    silently advect `min(n_particles, n_obs)` and report the request."""
    import numpy as np

    from varuna_integration import pipeline as pl

    def _too_few(detection, seed, *, n):
        return (np.full(12, detection.centroid.lon),
                np.full(12, detection.centroid.lat))

    monkeypatch.setattr(pl, "_slick_points_from_detection", _too_few)

    run = _scientific_pipeline(n_particles=500).run()
    phi = run.stages["phi_reconstruction"]
    assert phi.status is StageStatus.BLOCKED
    assert "PARTICLE_COUNT_UNDER_RESOLVED" in phi.reason
    assert "500" in phi.reason and "12" in phi.reason


def test_scientific_run_with_enough_points_is_not_blocked_by_the_guard():
    """The guard must not fire once the sampler draws the requested count."""
    run = _scientific_pipeline(n_particles=500).run()
    phi = run.stages["phi_reconstruction"]
    assert "PARTICLE_COUNT_UNDER_RESOLVED" not in (phi.reason or "")
    if phi.status is StageStatus.PRODUCED:
        assert phi.detail["n_particles_advected"] == 500
        assert phi.detail["n_particles_requested"] == 500
