"""
VARUNA GRID — packages.varuna_infra.observability tests (Phase 7,
VARUNA_PRODUCT_READY hardening session).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from varuna_contracts.evidence import EvidenceMode
from varuna_infra.observability import (
    MetricsTracker, build_case_timeline, summarize_case_state,
)
from varuna_integration.stage import StageResult, StageStatus


@dataclass
class _FakeRun:
    run_id: str
    case_id: str
    evidence_mode: EvidenceMode | None
    stages: dict = field(default_factory=dict)


def test_build_case_timeline_orders_stages_canonically():
    run = _FakeRun(
        run_id="RUN-1", case_id="CASE-1", evidence_mode=EvidenceMode.REAL,
        stages={
            "netra_detection": StageResult(
                stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
                reason="NO_SLICK_DETECTED", runtime_seconds=1.0,
            ),
            "forcing": StageResult(
                stage="forcing", status=StageStatus.PRODUCED, value={"ok": True},
                evidence_mode=EvidenceMode.REAL, runtime_seconds=0.5,
            ),
        },
    )
    timeline = build_case_timeline(run)
    assert [e["stage"] for e in timeline] == ["forcing", "netra_detection"]
    assert timeline[0]["status"] == "produced"
    assert timeline[1]["status"] == "not_yet_produced"
    assert timeline[1]["reason"] == "NO_SLICK_DETECTED"


def test_build_case_timeline_appends_unrecognized_stage():
    run = _FakeRun(
        run_id="RUN-2", case_id="CASE-2", evidence_mode=None,
        stages={
            "some_future_stage": StageResult(
                stage="some_future_stage", status=StageStatus.BLOCKED,
                reason="not wired yet",
            ),
        },
    )
    timeline = build_case_timeline(run)
    assert timeline[0]["stage"] == "some_future_stage"


def test_summarize_case_state_reports_first_unproduced_stage():
    run = _FakeRun(
        run_id="RUN-3", case_id="CASE-3", evidence_mode=EvidenceMode.SIMULATED,
        stages={
            "forcing": StageResult(
                stage="forcing", status=StageStatus.PRODUCED, value=1,
                evidence_mode=EvidenceMode.SIMULATED,
            ),
            "ais_ingest": StageResult(
                stage="ais_ingest", status=StageStatus.BLOCKED,
                reason="AIS_UNAVAILABLE",
            ),
            "netra_detection": StageResult(
                stage="netra_detection", status=StageStatus.NOT_YET_PRODUCED,
                reason="NO_SLICK_DETECTED",
            ),
        },
    )
    summary = summarize_case_state(run)
    assert summary["n_stages_produced"] == 1
    assert summary["n_stages_total"] == 3
    assert summary["first_unproduced_stage"]["stage"] == "ais_ingest"
    assert summary["first_unproduced_stage"]["reason"] == "AIS_UNAVAILABLE"


def test_summarize_case_state_none_when_all_produced():
    run = _FakeRun(
        run_id="RUN-4", case_id="CASE-4", evidence_mode=EvidenceMode.REAL,
        stages={
            "forcing": StageResult(stage="forcing", status=StageStatus.PRODUCED, value=1),
        },
    )
    summary = summarize_case_state(run)
    assert summary["first_unproduced_stage"] is None


def test_metrics_tracker_records_and_snapshots():
    MetricsTracker.reset()
    MetricsTracker.record_inference_time("netra-v0.2", 120.0)
    MetricsTracker.record_inference_time("netra-v0.2", 80.0)
    MetricsTracker.increment_error_count("forcing_adapter")
    MetricsTracker.increment_error_count("forcing_adapter")

    snap = MetricsTracker.snapshot()
    assert snap["inference_times_ms"]["netra-v0.2"]["count"] == 2
    assert snap["inference_times_ms"]["netra-v0.2"]["mean"] == 100.0
    assert snap["error_counts"]["forcing_adapter"] == 2
    MetricsTracker.reset()


def test_metrics_tracker_empty_histogram_summary():
    MetricsTracker.reset()
    snap = MetricsTracker.snapshot()
    assert snap["inference_times_ms"] == {}
    assert snap["error_counts"] == {}
