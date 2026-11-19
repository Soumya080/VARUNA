"""
Track 4 - fast boundary tests. No real data, no GPU, no network.

These cover the invariants that would let a demo lie: a provenance upgrade, a
silent mock fallback, a stage that fails without saying so, and a simulated
alert counted as delivered.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.schemas import BBox, GeoPoint
from varuna_integration.netra_boundary import (
    CheckpointFreezeStatus,
    FreezeRecord,
    NetraDetectionBoundary,
    NetraModelSpec,
    SimulatedSlickProvider,
    check_checkpoint_frozen,
    resolve_netra_boundary,
    sha256_of,
)
from varuna_integration.stage import StageResult, StageStatus, worst_mode


# ------------------------------- StageResult -------------------------------

def test_produced_requires_a_value():
    """PRODUCED with nothing in it is the shape a silent failure takes."""
    with pytest.raises(ValueError, match="PRODUCED requires a value"):
        StageResult(stage="x", status=StageStatus.PRODUCED)


@pytest.mark.parametrize("status", [StageStatus.BLOCKED, StageStatus.NOT_YET_PRODUCED])
def test_non_produced_requires_a_reason(status):
    with pytest.raises(ValueError, match="requires an explicit reason"):
        StageResult(stage="x", status=status)


# ------------------------------- worst_mode -------------------------------

@pytest.mark.parametrize("modes,expected", [
    ((EvidenceMode.REAL, EvidenceMode.REAL), EvidenceMode.REAL),
    ((EvidenceMode.REAL, EvidenceMode.SIMULATED), EvidenceMode.SIMULATED),
    ((EvidenceMode.SIMULATED, EvidenceMode.REAL), EvidenceMode.SIMULATED),
    ((EvidenceMode.REAL, EvidenceMode.UNAVAILABLE), EvidenceMode.UNAVAILABLE),
    ((EvidenceMode.SIMULATED, EvidenceMode.UNAVAILABLE), EvidenceMode.UNAVAILABLE),
    ((EvidenceMode.REAL, None), EvidenceMode.REAL),
    ((None, None), None),
])
def test_evidence_mode_only_worsens(modes, expected):
    assert worst_mode(*modes) is expected


def test_no_combination_of_inputs_produces_real_unless_all_are_real():
    """Phase 14's core claim, stated as a property over every pair."""
    all_modes = [EvidenceMode.REAL, EvidenceMode.SIMULATED, EvidenceMode.UNAVAILABLE]
    for a in all_modes:
        for b in all_modes:
            if worst_mode(a, b) is EvidenceMode.REAL:
                assert a is EvidenceMode.REAL and b is EvidenceMode.REAL


# ------------------------------- freeze gate -------------------------------

def _sim_provider() -> SimulatedSlickProvider:
    return SimulatedSlickProvider(
        centroid=GeoPoint(lon=-88.9, lat=28.9),
        bbox=BBox(min_lon=-89.0, min_lat=28.8, max_lon=-88.8, max_lat=29.0),
    )


def test_missing_checkpoint_is_not_frozen(tmp_path):
    st = check_checkpoint_frozen(tmp_path / "nope.pt")
    assert st.frozen is False
    assert "CHECKPOINT_MISSING" in st.reason


def test_checkpoint_without_freeze_record_is_not_frozen(tmp_path):
    """The live-training case: bytes exist, but nothing certifies them."""
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"weights")
    st = check_checkpoint_frozen(ck)
    assert st.frozen is False
    assert "CHECKPOINT_NOT_FROZEN" in st.reason


def test_freeze_record_with_wrong_hash_is_rejected(tmp_path):
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"weights")
    FreezeRecord.sidecar_path(ck).write_text(json.dumps({
        "checkpoint_sha256": "0" * 64,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "model_version": "v1",
        "metrics": {},
    }), encoding="utf-8")
    st = check_checkpoint_frozen(ck)
    assert st.frozen is False
    assert "CHECKPOINT_HASH_MISMATCH" in st.reason


def test_correctly_frozen_checkpoint_is_accepted(tmp_path):
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"weights")
    FreezeRecord.sidecar_path(ck).write_text(json.dumps({
        "checkpoint_sha256": sha256_of(ck),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "model_version": "v1",
        "metrics": {"iou_oil": 0.61},
    }), encoding="utf-8")
    st = check_checkpoint_frozen(ck)
    assert st.frozen is True
    assert st.record.metrics["iou_oil"] == 0.61


def test_a_checkpoint_edited_after_freezing_is_rejected(tmp_path):
    """Guards the actual hazard: reading a file training is still rewriting."""
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"epoch-30")
    FreezeRecord.sidecar_path(ck).write_text(json.dumps({
        "checkpoint_sha256": sha256_of(ck),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "model_version": "v1", "metrics": {},
    }), encoding="utf-8")
    assert check_checkpoint_frozen(ck).frozen is True
    ck.write_bytes(b"epoch-31")            # training writes another epoch
    assert check_checkpoint_frozen(ck).frozen is False


# --------------------------- no silent mock fallback ---------------------------

def test_unfrozen_checkpoint_yields_no_boundary_by_default(tmp_path):
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"weights")
    boundary, reason = resolve_netra_boundary(NetraModelSpec(checkpoint_path=ck))
    assert boundary is None, "an unfrozen checkpoint must not silently become a mock"
    assert "CHECKPOINT_NOT_FROZEN" in reason


def test_allow_simulated_still_requires_an_explicit_provider(tmp_path):
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"weights")
    boundary, reason = resolve_netra_boundary(
        NetraModelSpec(checkpoint_path=ck), allow_simulated=True)
    assert boundary is None
    assert "will not invent slick geometry" in reason


def test_explicitly_requested_simulation_is_labelled_simulated(tmp_path):
    ck = tmp_path / "model.pt"
    ck.write_bytes(b"weights")
    boundary, reason = resolve_netra_boundary(
        NetraModelSpec(checkpoint_path=ck),
        allow_simulated=True, simulated_provider=_sim_provider())
    assert boundary is not None
    assert boundary.evidence_mode is EvidenceMode.SIMULATED
    assert reason.startswith("SIMULATED")


def test_simulated_provider_can_never_be_labelled_real():
    with pytest.raises(ValueError, match="may never be labelled REAL"):
        NetraDetectionBoundary(_sim_provider(), EvidenceMode.REAL, source_id="x")


def test_simulated_detection_asserts_no_confidence_and_no_oil_class():
    """A placeholder must not look like a positive oil detection."""
    from varuna_contracts.evidence import EvidenceEnvelope, Provenance
    from varuna_contracts.schemas import SlickClass

    env = EvidenceEnvelope(artifact_id="a", produced_by="t",
                           provenance=Provenance(source_id="t"),
                           mode=EvidenceMode.SIMULATED)
    det = _sim_provider().detect("unused", None, env)[0]
    assert det.confidence == 0.0
    assert det.classification is not SlickClass.OIL
    assert "SIMULATED" in det.netra_model_version


def test_no_tiles_reports_not_yet_produced_not_an_empty_success():
    boundary = NetraDetectionBoundary(
        _sim_provider(), EvidenceMode.SIMULATED, source_id="sim")
    res = boundary.detect_tiles([], case_id="c")
    assert res.status is StageStatus.NOT_YET_PRODUCED
    assert "NO_SAR_TILES" in res.reason


def test_inference_failure_becomes_blocked_not_an_exception(tmp_path):
    """Phase 13: a producer blowing up must not crash the case."""
    class Exploding(SimulatedSlickProvider):
        def detect(self, scene_path, wind_path, envelope):
            raise RuntimeError("CUDA error")

    boundary = NetraDetectionBoundary(
        Exploding(centroid=GeoPoint(lon=0.0, lat=0.0),
                  bbox=BBox(min_lon=-1, min_lat=-1, max_lon=1, max_lat=1)),
        EvidenceMode.SIMULATED, source_id="sim")
    res = boundary.detect_tiles([tmp_path / "t.npy"], case_id="c")
    assert res.status is StageStatus.BLOCKED
    assert "NETRA_INFERENCE_FAILED" in res.reason
    assert "CUDA error" in res.reason


# --------------------- upstream status propagation (Phase 13) ---------------------

def _run_with(stage_name, status, reason):
    from varuna_integration.pipeline import PipelineConfig, PipelineRun
    from datetime import datetime, timezone
    from pathlib import Path

    run = PipelineRun(run_id="R", case_id="C", started_at=datetime.now(timezone.utc),
                      config=PipelineConfig(gold_dir=Path(".")))
    run.record(StageResult(stage=stage_name, status=status, reason=reason))
    return run


def test_not_yet_produced_upstream_does_not_become_blocked_downstream():
    """"The model found no oil" must not render as "the pipeline is broken"."""
    run = _run_with("phi_reconstruction", StageStatus.NOT_YET_PRODUCED, "NO_SLICK_GEOMETRY")
    result = run.blocked_by("attribution", "phi_reconstruction", "NO_SLICK_GEOMETRY")
    assert result.status is StageStatus.NOT_YET_PRODUCED
    assert run.blocked_at is None, "a clean no-detection run must report no blockage"


def test_blocked_upstream_stays_blocked_downstream():
    """A genuine integration break must still propagate as BLOCKED."""
    run = _run_with("forcing", StageStatus.BLOCKED, "CMEMS_CUBE_MISSING")
    result = run.blocked_by("phi_reconstruction", "forcing", "CMEMS_CUBE_MISSING")
    assert result.status is StageStatus.BLOCKED
    assert run.blocked_at is not None


def test_unknown_upstream_defaults_to_blocked():
    """Absent evidence about the upstream must fail closed, not open."""
    run = _run_with("forcing", StageStatus.BLOCKED, "irrelevant")
    result = run.blocked_by("decision", "never_ran", "no record for that stage")
    assert result.status is StageStatus.BLOCKED


# ------------------------------ forcing fail-closed ------------------------------

def test_forcing_missing_directory_is_blocked_and_unavailable(tmp_path):
    from varuna_integration.forcing import load_event_forcing

    res = load_event_forcing(tmp_path / "no_such_event")
    assert res.status is StageStatus.BLOCKED
    assert res.evidence_mode is EvidenceMode.UNAVAILABLE
    assert "ERA5_CUBE_MISSING" in res.reason


# ------------------------------ AIS join semantics ------------------------------

def test_spatial_candidacy_is_never_promoted_to_temporal_evidence():
    """A record claiming TEMPORALLY_MATCHED while its own flag says otherwise
    must degrade, not be believed."""
    from varuna_integration.ais_source import AISJoinStatus, AISTrackJoin

    join = AISTrackJoin.from_record({
        "track_id": "t1", "mmsi": "1", "status": "TEMPORALLY_MATCHED",
        "spatially_matched": True, "temporally_matched": False,
        "n_points": 10, "n_points_in_sar_footprint": 10,
        "closest_distance_km": 1.0, "closest_point_timestamp": None,
        "closest_time_delta_seconds": None,
    })
    assert join.status is AISJoinStatus.SPATIALLY_MATCHED_ONLY
    assert join.status.is_temporal_evidence is False


def test_unknown_join_status_degrades_to_the_weakest_claim():
    from varuna_integration.ais_source import AISJoinStatus, AISTrackJoin

    join = AISTrackJoin.from_record({
        "track_id": "t", "mmsi": "1", "status": "SOMETHING_NEW",
        "spatially_matched": True, "temporally_matched": True,
        "n_points": 2, "n_points_in_sar_footprint": 2,
        "closest_distance_km": None, "closest_point_timestamp": None,
        "closest_time_delta_seconds": None,
    })
    assert join.status is AISJoinStatus.NOT_MATCHED


def test_only_temporally_matched_counts_as_temporal_evidence():
    from varuna_integration.ais_source import AISJoinStatus

    temporal = [s for s in AISJoinStatus if s.is_temporal_evidence]
    assert temporal == [AISJoinStatus.TEMPORALLY_MATCHED]


# ------------------------------ case bridge ------------------------------

def test_bridge_never_defaults_a_missing_mode_to_real():
    from varuna_integration.case_bridge import section_payload

    payload = section_payload(StageResult(
        stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
        reason="no model"))
    assert payload["evidence_mode"] is None
    assert payload["value"] is None
    assert payload["reason"] == "no model"


def test_bridge_carries_simulated_through_verbatim():
    from varuna_integration.case_bridge import section_payload

    payload = section_payload(StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[1],
        evidence_mode=EvidenceMode.SIMULATED))
    assert payload["evidence_mode"] == "simulated"


# --------------------------- particle-count honesty ---------------------------
# `run_backward_ensemble` subsamples with `min(n_particles, n_obs)` and does so
# silently. These pin the two halves of the fix: enough points get drawn, and a
# run that would still be under-resolved refuses the SCIENTIFIC label rather
# than reporting a particle count it did not achieve.

class _Det:
    """Minimal stand-in carrying only the geometry the sampler reads."""
    centroid = GeoPoint(lon=-88.9, lat=28.9)
    bbox = BBox(min_lon=-89.0, min_lat=28.8, max_lon=-88.8, max_lat=29.0)


def test_observation_points_honour_the_requested_particle_count():
    from varuna_integration.pipeline import _slick_points_from_detection

    lons, lats = _slick_points_from_detection(_Det(), seed=42, n=500)
    assert len(lons) == 500 and len(lats) == 500


def test_sampler_has_no_default_particle_count():
    """A default here is what let a requested 500 silently advect 12."""
    import inspect
    from varuna_integration.pipeline import _slick_points_from_detection

    param = inspect.signature(_slick_points_from_detection).parameters["n"]
    assert param.default is inspect.Parameter.empty
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_sampled_points_stay_inside_the_real_detected_bbox():
    from varuna_integration.pipeline import _slick_points_from_detection

    bb = _Det.bbox
    lons, lats = _slick_points_from_detection(_Det(), seed=7, n=500)
    assert lons.min() >= bb.min_lon and lons.max() <= bb.max_lon
    assert lats.min() >= bb.min_lat and lats.max() <= bb.max_lat


def test_phi_detail_reports_advected_and_requested_particles_separately():
    """The detail block must expose both counts; the bare `n_particles` key
    conflated the request with the result."""
    import inspect
    from varuna_integration import pipeline

    src = inspect.getsource(pipeline)
    assert '"n_particles_advected"' in src
    assert '"n_particles_requested"' in src


def test_under_resolved_scientific_run_is_blocked_with_a_named_reason():
    """A SCIENTIFIC run whose points cannot fill the requested particle count
    must block, not quietly advect fewer and report the request."""
    import inspect
    from varuna_integration import pipeline

    src = inspect.getsource(pipeline)
    assert "PARTICLE_COUNT_UNDER_RESOLVED" in src
    assert "n_particles_advected = min(cfg.n_particles, len(slick_lons))" in src
    assert "if cfg.is_scientific and n_particles_advected < cfg.n_particles:" in src
