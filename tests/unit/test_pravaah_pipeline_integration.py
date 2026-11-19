"""
PRAVAAH canonical case integration -- focused tests for
`RealE2EPipeline._forecast()` (packages/varuna_integration/pipeline.py).

These exercise the stage in isolation via constructed StageResults, so most
of them need no real data and no GPU. The two real-MC20 tests skip cleanly
when the (gitignored) Event Gold corpus is absent, matching this repo's
existing convention (see tests/integration/test_track4_mc20_e2e.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.schemas import BBox, GeoPoint, SlickClass, SlickDetection
from varuna_integration.pipeline import PipelineConfig, PipelineRun, RealE2EPipeline
from varuna_integration.stage import StageResult, StageStatus

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"


def _run(case_id: str = "TEST-CASE") -> PipelineRun:
    return PipelineRun(
        run_id="RUN-TEST", case_id=case_id, started_at=datetime.now(timezone.utc),
        config=PipelineConfig(gold_dir=GOLD),
    )


def _pipeline() -> RealE2EPipeline:
    return RealE2EPipeline(PipelineConfig(gold_dir=GOLD))


def _detection(mode_note: str = "test", **overrides) -> SlickDetection:
    defaults = dict(
        slick_id="slick-1", scene_id="scene-1",
        observation_time=datetime(2023, 1, 15, tzinfo=timezone.utc),
        classification=SlickClass.OIL, confidence=0.9, mask_path="m.tif",
        centroid=GeoPoint(lon=-89.5, lat=29.0),
        bbox=BBox(min_lon=-89.6, min_lat=28.9, max_lon=-89.4, max_lat=29.1),
        area_km2=5.0, perimeter_km=10.0, elongation=2.0, orientation_deg=0.0,
        age_prior_mean_hours=24.0, age_prior_std_hours=12.0,
        netra_model_version=mode_note,
    )
    defaults.update(overrides)
    return SlickDetection(**defaults)


def _validity_stub() -> StageResult:
    # _forecast() takes validity_res only to pass through untouched -- it does
    # not read it (PRAVAAH depends on forcing+detection, not on the gate's
    # verdict or on Phi/origin -- see test_forecast_does_not_depend_on_phi_or_validity).
    return StageResult(stage="validity", status=StageStatus.NOT_YET_PRODUCED, reason="n/a")


# ------------------------- Phase 9.2/9.4: forcing missing/unavailable -------------------------

def test_forcing_not_produced_blocks_forecast_naming_the_upstream_stage():
    pipeline = _pipeline()
    run = _run()
    forcing_res = StageResult(
        stage="forcing", status=StageStatus.BLOCKED,
        reason="FORCING_MISSING: no ERA5/CMEMS cubes for this event.",
    )
    detection_res = StageResult(stage="netra_detection", status=StageStatus.PRODUCED,
                                value=[_detection()], evidence_mode=EvidenceMode.SIMULATED)
    result = pipeline._forecast(run, forcing_res, detection_res, _validity_stub())
    assert result.status is StageStatus.BLOCKED
    assert "forcing" in result.reason.lower()
    assert result.reason  # named, not empty


# ------------------------------ NO_SLICK_TO_FORECAST ------------------------------

def test_detection_not_produced_yields_not_yet_produced_not_an_error():
    pipeline = _pipeline()
    run = _run()
    forcing_res = StageResult(stage="forcing", status=StageStatus.PRODUCED, value=object(),
                              evidence_mode=EvidenceMode.REAL)
    detection_res = StageResult(
        stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
        reason="NO_SLICK_DETECTED: the model ran on 9 tile(s) and returned no detection.",
    )
    result = pipeline._forecast(run, forcing_res, detection_res, _validity_stub())
    assert result.status is StageStatus.NOT_YET_PRODUCED
    assert "NO_SLICK_TO_FORECAST" in result.reason
    assert "NO_SLICK_DETECTED" in result.reason  # upstream reason chained through, not dropped


# ---------------------- Phase 9.7: malformed upstream result ----------------------

def test_detection_produced_but_empty_value_list_fails_closed_not_indexerror():
    """
    Regression test for a real gap this integration pass found and fixed:
    `detection_res.value[0]` used to run unguarded before any try/except,
    so `status=PRODUCED, value=[]` (unreachable via
    NetraDetectionBoundary.detect_tiles() today, but not defended against
    here) would have raised an uncaught IndexError, crashing the whole
    pipeline run instead of failing closed with a named reason.
    """
    pipeline = _pipeline()
    run = _run()
    forcing_res = StageResult(stage="forcing", status=StageStatus.PRODUCED, value=object(),
                              evidence_mode=EvidenceMode.REAL)
    detection_res = StageResult(
        stage="netra_detection", status=StageStatus.PRODUCED, value=[],
        evidence_mode=EvidenceMode.REAL,
    )
    result = pipeline._forecast(run, forcing_res, detection_res, _validity_stub())
    assert result.status is StageStatus.BLOCKED
    assert "MALFORMED_DETECTION_RESULT" in result.reason


# --------------------- Phase 9.7 variant: PRAVAAH raises mid-call ---------------------

def test_pravaah_exception_is_blocked_with_a_named_reason_not_propagated():
    pipeline = _pipeline()
    run = _run()

    class _ExplodingCurrentField:
        _u_grid = None
        _v_grid = None

    class _FakeForcing:
        current_field = _ExplodingCurrentField()
        cmems_cube = None
        from varuna_contracts.evidence import EvidenceEnvelope, Provenance
        envelope = EvidenceEnvelope(
            artifact_id="forcing-x", produced_by="test",
            provenance=Provenance(source_id="test"), mode=EvidenceMode.REAL,
        )

    forcing_res = StageResult(stage="forcing", status=StageStatus.PRODUCED,
                              value=_FakeForcing(), evidence_mode=EvidenceMode.REAL)
    detection_res = StageResult(stage="netra_detection", status=StageStatus.PRODUCED,
                                value=[_detection()], evidence_mode=EvidenceMode.REAL)
    result = pipeline._forecast(run, forcing_res, detection_res, _validity_stub())
    assert result.status is StageStatus.BLOCKED
    assert "PRAVAAH_FAILED" in result.reason


# --------------- Phase 9.6: PRAVAAH does not depend on Phi/origin/validity ---------------

def test_forecast_signature_does_not_take_phi_or_origin():
    """
    Forward drift starts from the DETECTED slick's own position, not from
    PRATIVARTAN's backward-reconstructed origin -- these are two different
    starting points by design (see
    tests/unit/test_replay_fixtures.py::test_case_blocked_is_a_scoped_break_not_a_blanket_one,
    which proves a PRATIVARTAN BLOCKED does not block forecast). This is a
    structural fact about the current architecture, not something this
    integration pass changed or should change -- documented, not silently
    assumed.
    """
    import inspect
    params = list(inspect.signature(RealE2EPipeline._forecast).parameters)
    assert "phi_res" not in params
    assert set(params) == {"self", "run", "forcing_res", "detection_res", "validity_res"}


# ----------------------------- Real MC20 forcing path -----------------------------

pytestmark_real = pytest.mark.skipif(
    not (GOLD / "manifest.json").exists(),
    reason="MC20 Event Gold is not present in this checkout (gitignored corpus)",
)


@pytestmark_real
def test_real_forcing_plus_real_detection_produces_real_forecast_with_case_id():
    """
    REAL forcing + REAL-mode detection must yield a REAL forecast envelope
    carrying the real case_id -- the positive-path complement to the
    SIMULATED-worsening test in
    tests/integration/test_golden_case_engine_mc20_e2e.py.
    """
    from varuna_integration.forcing import load_event_forcing

    pipeline = _pipeline()
    case_id = "TEST-REAL-CASE-001"
    run = _run(case_id)
    forcing_res = load_event_forcing(GOLD)
    assert forcing_res.produced, forcing_res.reason
    manifest_bbox = forcing_res.value.cmems_cube.bbox
    clon = (manifest_bbox.min_lon + manifest_bbox.max_lon) / 2
    clat = (manifest_bbox.min_lat + manifest_bbox.max_lat) / 2
    detection = _detection(
        centroid=GeoPoint(lon=clon, lat=clat),
        bbox=BBox(min_lon=clon - 0.05, min_lat=clat - 0.05, max_lon=clon + 0.05, max_lat=clat + 0.05),
        observation_time=datetime(2023, 1, 15, 0, 2, tzinfo=timezone.utc),
    )
    detection_res = StageResult(stage="netra_detection", status=StageStatus.PRODUCED,
                                value=[detection], evidence_mode=EvidenceMode.REAL)

    result = pipeline._forecast(run, forcing_res, detection_res, _validity_stub())

    assert result.status is StageStatus.PRODUCED, result.reason
    forecast = result.value
    assert result.evidence_mode == EvidenceMode.REAL
    assert forecast.envelope.mode == EvidenceMode.REAL
    assert forecast.envelope.case_id == case_id
    assert forecast.envelope.provenance is not None
    assert Path(forecast.trajectory_path).exists()
    assert forecast.horizon_hours == pipeline.config.forecast_horizon_hours
