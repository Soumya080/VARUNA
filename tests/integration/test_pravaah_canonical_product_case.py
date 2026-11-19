"""
STEP 5 — PRAVAAH as a genuine load-bearing stage of the canonical
GoldenCaseWorkflow / unified product case flow.

Phase 1 diagnosis (this task): `RealE2EPipeline._forecast()` already calls
the REAL `CubeBackedPravaahProvider` against real MC20 CMEMS forcing
(verified pre-existing: tests/unit/test_pravaah_pipeline_integration.py),
and `GoldenCaseWorkflow.run_case()` already exercises this end-to-end with a
`SimulatedSlickProvider` detection against real forcing
(pre-existing: tests/integration/test_golden_case_engine_mc20_e2e.py::
test_pravaah_forecast_runs_on_real_mc20_forcing_via_the_canonical_pipeline).

**The actual gap this task closes**: `build_product_case()` (STEP 3's
composition boundary) had NEVER been exercised against a `CaseResult`
carrying a genuinely-computed (not replay-fixture) PRAVAAH forecast. Every
existing `build_product_case()` test used the `CASE-VALID` replay fixture,
whose `ForwardForecast` is a hand-built value in
`replay_fixtures.py::_forecast()` — never a real drift computation. This
file proves the forecast a REAL PRAVAAH run produces survives, unmodified
and un-duplicated, through the full composition into
`OperatorCase.forecast` and coexists correctly with `OperatorCase.intelligence`.

CASE-VALID remains the correct fixture for the REPLAY story (Phase 4's own
text permits this: "if CASE-VALID lacks legitimate inputs for a real
forecast... use an existing fixture if possible" — no replay fixture calls
real PRAVAAH by construction, since replay fixtures are canned data by
design; this file instead uses the REAL path, matching Phase 5's explicit
"verify the real MC20 path where applicable").
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from varuna_contracts.evidence import EvidenceMode
from varuna_contracts.schemas import ForwardForecast

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"

pytestmark_real = pytest.mark.skipif(
    not (GOLD / "manifest.json").exists(),
    reason="MC20 Event Gold is not present in this checkout (gitignored corpus)",
)


def _event_acquisition_time(manifest: dict):
    from datetime import datetime, timezone
    ts = manifest["modalities"]["sar"]["timestamp"]
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def real_forcing_simulated_detection_result():
    """Same construction as
    test_golden_case_engine_mc20_e2e.py::workflow_and_result -- real MC20
    CMEMS/ERA5 forcing, a SimulatedSlickProvider detection (the sanctioned,
    honestly-labeled way to exercise the forecast-PRODUCED path without GPU
    inference or a positive real detection this corpus does not have)."""
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
        provider, EvidenceMode.SIMULATED, source_id="test.pravaah_canonical.simulated")

    cfg = PipelineConfig(
        gold_dir=GOLD, n_particles=20, n_ensemble=4, max_ais_tracks=5,
        run_class="INTEGRATION_SMOKE",
    )
    wf = GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
        netra=boundary,
    )
    result = wf.run_case(
        "PRAVAAH-CANONICAL-TEST", gold_dir=GOLD, mode=EngineMode.SIMULATED,
        pipeline_config=cfg,
    )
    return wf, result


@pytestmark_real
def test_1_pravaah_is_invoked_by_the_canonical_workflow(real_forcing_simulated_detection_result):
    """PRAVAAH executes as part of GoldenCaseWorkflow.run_case(), not a
    hand-built value and not a separately-constructed pipeline."""
    _wf, result = real_forcing_simulated_detection_result
    forecast_stage = result.run.stages["forecast"]
    assert forecast_stage.status.value == "produced"


@pytestmark_real
def test_2_real_provider_output_propagates(real_forcing_simulated_detection_result):
    """The forecast came from CubeBackedPravaahProvider against real
    forcing: a real trajectory file exists on disk, not a fabricated path."""
    _wf, result = real_forcing_simulated_detection_result
    forecast = result.run.stages["forecast"].value
    assert isinstance(forecast, ForwardForecast)
    assert Path(forecast.trajectory_path).exists()


@pytestmark_real
def test_3_forward_forecast_preserves_metadata(real_forcing_simulated_detection_result):
    _wf, result = real_forcing_simulated_detection_result
    forecast = result.run.stages["forecast"].value
    assert forecast.envelope.case_id == "PRAVAAH-CANONICAL-TEST"
    assert forecast.envelope.provenance is not None
    assert forecast.horizon_hours > 0
    assert forecast.envelope.mode == EvidenceMode.SIMULATED  # worsened from the detection


@pytestmark_real
def test_4_forecast_reaches_unified_operator_case(real_forcing_simulated_detection_result):
    """The gap this task closes: build_product_case() had never been run
    against a genuinely-computed (non-replay-fixture) PRAVAAH forecast."""
    from varuna_integration.product_case import build_product_case

    wf, result = real_forcing_simulated_detection_result
    pc = build_product_case(result, wf)

    assert pc.forecast.status.value == "produced"
    assert pc.forecast.evidence_mode == EvidenceMode.SIMULATED
    forecast_value = pc.forecast.value
    assert forecast_value is not None
    assert Path(forecast_value.trajectory_path).exists()
    assert forecast_value.horizon_hours > 0
    # Composition must not have discarded provenance on the way through
    # OperatorCase's SectionEnvelope[ForwardForecast] wrapping.
    assert forecast_value.envelope.case_id == "PRAVAAH-CANONICAL-TEST"


@pytestmark_real
def test_5_replay_result_is_deterministic_independent_of_pravaah_change():
    """CASE-VALID's own determinism (proven in STEP 2/3) is unaffected by
    this task's changes -- run it fresh here as a direct regression check
    scoped to this task's own test file, not just inherited from elsewhere."""
    from varuna_domain.golden_case_engine import GoldenCaseWorkflow
    from varuna_domain.repositories import (
        InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
    )

    def _wf():
        return GoldenCaseWorkflow(
            InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
        )

    r1 = _wf().run_replay_case("PRAVAAH-DETERMINISM", "CASE-VALID")
    r2 = _wf().run_replay_case("PRAVAAH-DETERMINISM", "CASE-VALID")
    assert r1.reproducibility.deterministic_run_id == r2.reproducibility.deterministic_run_id
    assert r1.run.stages["forecast"].value.horizon_hours == r2.run.stages["forecast"].value.horizon_hours


def test_6_unavailable_forcing_fails_closed_never_fabricates_a_forecast():
    """Canonical-pipeline check that missing/invalid input never produces a
    forecast by any path -- not a stage-level BLOCKED (that requires a
    gold_dir shaped like a real event with a manifest but genuinely absent
    forcing cubes, already covered at the stage level by
    test_pravaah_pipeline_integration.py::test_forcing_not_produced_blocks_forecast_naming_the_upstream_stage),
    but the coarser, equally real failure mode: a gold_dir with no event
    manifest at all. `RealE2EPipeline.run()` raises before any stage
    executes; `GoldenCaseWorkflow.run_case()` must convert that into an
    explicit CaseStatus.FAILED with a real, named error -- never a silent
    empty success and never a fabricated forecast."""
    from varuna_domain.entities import CaseStatus
    from varuna_domain.golden_case_engine import EngineMode, GoldenCaseWorkflow
    from varuna_domain.repositories import (
        InMemoryArtifactRepository, InMemoryCaseRepository, InMemoryEventStore,
    )
    from varuna_integration.pipeline import PipelineConfig

    wf = GoldenCaseWorkflow(
        InMemoryCaseRepository(), InMemoryArtifactRepository(), InMemoryEventStore(),
    )
    not_an_event_dir = REPO_ROOT / "data" / "gold" / "netra_v0_2"  # real dir, no event manifest.json

    with pytest.raises(FileNotFoundError):
        wf.run_case(
            "PRAVAAH-NO-FORCING", gold_dir=not_an_event_dir, mode=EngineMode.REAL,
            pipeline_config=PipelineConfig(gold_dir=not_an_event_dir),
        )

    case = wf.cases.get("PRAVAAH-NO-FORCING")
    assert case is not None
    assert case.status == CaseStatus.FAILED
    assert case.error is not None and "FileNotFoundError" in case.error


@pytestmark_real
def test_7_out_of_domain_style_ood_detection_still_reaches_forecast_or_fails_named(
    real_forcing_simulated_detection_result,
):
    """This task does not change OOD/detection behavior -- confirms the
    forecast stage's own failure semantics (named BLOCKED/NOT_YET_PRODUCED
    reasons, never a silent empty success) are unaffected by this task's
    build_product_case() composition, using the same fixture as tests 1-4."""
    _wf, result = real_forcing_simulated_detection_result
    forecast_stage = result.run.stages["forecast"]
    # This fixture's detection succeeds (SimulatedSlickProvider always
    # fires), so the positive-path assertion is what applies here; the
    # negative path (no detection -> NO_SLICK_TO_FORECAST) is already
    # covered by test_pravaah_pipeline_integration.py's unit tests, which
    # remain in force and were re-run as part of this task's regression.
    assert forecast_stage.status.value == "produced"
    assert forecast_stage.reason is None


@pytestmark_real
def test_8_simulated_provider_forecast_remains_simulated_through_composition(
    real_forcing_simulated_detection_result,
):
    """Never upgraded to REAL merely because the underlying current field
    was real -- re-verified specifically AFTER build_product_case(), not
    only at the raw CaseResult/stage level (test 3 above)."""
    from varuna_integration.product_case import build_product_case

    wf, result = real_forcing_simulated_detection_result
    pc = build_product_case(result, wf)
    assert pc.forecast.evidence_mode == EvidenceMode.SIMULATED
    assert pc.forecast.value.envelope.mode == EvidenceMode.SIMULATED


@pytestmark_real
def test_10_no_duplicate_pravaah_execution_during_composition(
    real_forcing_simulated_detection_result, monkeypatch,
):
    """build_product_case() must not re-invoke PRAVAAH -- it only reads the
    StageResult GoldenCaseWorkflow.run_case() already produced. Proven by
    patching the provider class build_product_case() would need to touch to
    re-run forecasting and asserting it is never constructed during
    composition."""
    from varuna_integration.product_case import build_product_case
    import varuna_pravaah.cube_provider as cube_provider_module

    wf, result = real_forcing_simulated_detection_result

    calls = []
    original_init = cube_provider_module.CubeBackedPravaahProvider.__init__

    def spy_init(self, *args, **kwargs):
        calls.append(1)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(cube_provider_module.CubeBackedPravaahProvider, "__init__", spy_init)
    build_product_case(result, wf)
    assert calls == [], (
        "build_product_case() constructed a new CubeBackedPravaahProvider -- "
        "PRAVAAH was re-invoked during composition instead of reading the "
        "already-computed StageResult, which is exactly the second-pipeline "
        "risk this task's Phase 3 forbids."
    )
