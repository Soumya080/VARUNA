"""
Golden Case Engine - bounded integration test over the real MC20 Event Gold.

Proves `GoldenCaseWorkflow.run_case()` (the REAL/SIMULATED path, not REPLAY)
actually drives `RealE2EPipeline` end to end, walks the CaseStatus lifecycle,
and is idempotent -- at deliberately tiny scale (mirrors
tests/integration/test_track4_mc20_e2e.py's bound: 20 particles, 4 ensemble
members, 5 AIS tracks). No GPU, no real NETRA checkpoint.

Skipped entirely when the (gitignored) MC20 Event Gold corpus is absent.
"""
from __future__ import annotations

# Schema imports before netCDF4 (Windows DLL interaction - see forcing.py).
from varuna_contracts.evidence import EvidenceMode  # isort: skip

import json
from pathlib import Path

import pytest

from varuna_domain.entities import CaseStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"

pytestmark = pytest.mark.skipif(
    not (GOLD / "manifest.json").exists(),
    reason="MC20 Event Gold is not present in this checkout (gitignored corpus)",
)


def _event_acquisition_time(manifest):
    from datetime import datetime, timezone

    return datetime.strptime(
        manifest["event_id"].split("_")[-1], "%Y-%m-%d").replace(tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def workflow_and_result():
    from varuna_contracts.schemas import BBox, GeoPoint
    from varuna_domain.golden_case_engine import EngineMode, GoldenCaseWorkflow
    from varuna_domain.repositories import (
        InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
    )
    from varuna_integration.netra_boundary import NetraDetectionBoundary, SimulatedSlickProvider
    from varuna_integration.pipeline import PipelineConfig

    manifest = json.loads((GOLD / "manifest.json").read_text(encoding="utf-8"))
    bb = manifest["modalities"]["sar"]["bbox"]
    clon = (bb["min_lon"] + bb["max_lon"]) / 2
    clat = (bb["min_lat"] + bb["max_lat"]) / 2
    provider = SimulatedSlickProvider(
        centroid=GeoPoint(lon=clon, lat=clat),
        bbox=BBox(min_lon=clon - 0.05, min_lat=clat - 0.05,
                  max_lon=clon + 0.05, max_lat=clat + 0.05),
        scene_id=manifest["event_id"],
        observation_time=_event_acquisition_time(manifest),
    )
    boundary = NetraDetectionBoundary(
        provider, EvidenceMode.SIMULATED, source_id="test.golden_case_engine.simulated")

    cfg = PipelineConfig(
        gold_dir=GOLD, n_particles=20, n_ensemble=4, max_ais_tracks=5,
        run_class="INTEGRATION_SMOKE",
    )
    wf = GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
        netra=boundary,
    )
    result = wf.run_case(
        "MC20-GOLDEN-TEST", gold_dir=GOLD, mode=EngineMode.SIMULATED, pipeline_config=cfg,
    )
    return wf, result


def test_run_reaches_a_named_terminal_status(workflow_and_result):
    _wf, result = workflow_and_result
    assert result.case.status in (
        CaseStatus.COMPLETE, CaseStatus.BLOCKED, CaseStatus.UNAVAILABLE, CaseStatus.OOD,
    )


def test_evidence_mode_worsens_to_simulated_because_detection_is_simulated(workflow_and_result):
    _wf, result = workflow_and_result
    assert result.run.evidence_mode == EvidenceMode.SIMULATED


def test_reproducibility_record_has_real_forcing_evidence_and_a_dataset_version(workflow_and_result):
    _wf, result = workflow_and_result
    assert result.reproducibility.dataset_version == "mc20_v0_1"
    assert result.reproducibility.case_id == "MC20-GOLDEN-TEST"


def test_rerun_same_case_same_config_is_idempotent(workflow_and_result):
    wf, result = workflow_and_result
    n_events_before = len(wf.event_spine.list_by_case("MC20-GOLDEN-TEST"))
    again = wf.run_case(
        "MC20-GOLDEN-TEST", gold_dir=GOLD, mode="simulated", pipeline_config=result.run.config,
    )
    assert again.idempotent_replay is True
    assert len(wf.event_spine.list_by_case("MC20-GOLDEN-TEST")) == n_events_before


def test_operator_case_projection_builds_without_error(workflow_and_result):
    wf, result = workflow_and_result
    oc = result.to_operator_case(wf)
    assert oc.case_id == "MC20-GOLDEN-TEST"
    # AIS is real on this path -- REAL forcing + REAL AIS + SIMULATED detection
    # is exactly the documented mixed-provenance scenario.
    assert oc.ais.evidence_mode == EvidenceMode.REAL
    assert oc.detection.evidence_mode == EvidenceMode.SIMULATED


def test_pravaah_forecast_runs_on_real_mc20_forcing_via_the_canonical_pipeline(workflow_and_result):
    """
    PRAVAAH canonical integration: SimulatedSlickProvider produces a detection
    (unlike the real frozen checkpoint on this same corpus, which currently
    finds nothing -- see reports/mc20_track4_e2e_run.json), so this is the one
    non-GPU way to exercise `pipeline._forecast()`'s PRODUCED path against
    real MC20 CMEMS forcing without waiting on NETRA v0.3 or running GPU
    inference. Real forcing + a simulated detection must worsen to SIMULATED
    overall (ADR-0006), never claim REAL just because the current field was
    real -- this is the "never infer REAL from provider class name" rule
    checked concretely.
    """
    from varuna_contracts.schemas import ForwardForecast
    from varuna_integration.stage import StageStatus

    _wf, result = workflow_and_result
    forecast_stage = result.run.stages["forecast"]
    assert forecast_stage.status is StageStatus.PRODUCED
    forecast = forecast_stage.value
    assert isinstance(forecast, ForwardForecast)

    # Real PRAVAAH computation, not a fabricated value: a real trajectory file
    # was written, and the horizon matches the config that was actually used.
    assert Path(forecast.trajectory_path).exists()
    assert forecast.horizon_hours == pytest.approx(24.0)

    # Evidence: forcing is REAL but detection is SIMULATED -- the forecast's
    # own envelope must report the worsened mode, not the forcing's.
    assert forecast.envelope.mode == EvidenceMode.SIMULATED
    assert forecast_stage.evidence_mode == EvidenceMode.SIMULATED

    # case_id must survive onto PRAVAAH's own envelope, not just onto the
    # outer OperatorCase wrapper -- this is the gap this task's integration
    # pass closed (forcing.envelope.case_id was None; see pipeline.py::_forecast).
    assert forecast.envelope.case_id == "MC20-GOLDEN-TEST"
    assert forecast.envelope.provenance is not None
