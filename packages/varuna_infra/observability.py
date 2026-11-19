"""
VARUNA GRID — observability (Phase 7, VARUNA_PRODUCT_READY hardening session).

Prior state: this module was 13 lines, `MetricsTracker.record_inference_time`
and `.increment_error_count` were both literally `pass # Stub`, and a
repo-wide search found zero callers of `setup_observability()` or
`MetricsTracker` anywhere in `packages/` or `apps/`. There was no gap to
"harden" — this was an unused stub.

What this module now provides, deliberately kept to "simple + useful +
structured" rather than a distributed tracing platform:

1. `configure_logging()` — real structured (JSON-line) logging, with
   `case_id`/`run_id`/`stage` bound via `logging.LoggerAdapter` rather than
   left to be threaded through every format string by hand.
2. `MetricsTracker` — a real in-memory counter/histogram store (not a
   pass-through stub). Still process-local and not wired to a metrics
   backend (Prometheus, etc.) — that wiring is a deployment concern out of
   scope here, and is named in the completion report as a follow-on, not
   silently implied to exist.
3. `build_case_timeline()` — the piece that actually answers "why is this
   case in this state" without reading source: it reads the SAME
   `StageResult` objects the pipeline already produces
   (`varuna_integration.pipeline.PipelineRun.stages`) and turns them into an
   ordered, human-readable timeline. This is not a new data source — every
   field it reads already existed on `StageResult`; nothing here recomputes
   or re-derives a stage's outcome.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any


def configure_logging(level: int = logging.INFO) -> None:
    """Structured (JSON-line) logging. Idempotent: calling it twice does not
    duplicate handlers, which a naive `basicConfig()` call would."""
    root = logging.getLogger()
    if any(isinstance(h, logging.StreamHandler) and
           getattr(h, "_varuna_structured", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler._varuna_structured = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("case_id", "run_id", "stage", "correlation_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def case_logger(logger: logging.Logger, *, case_id: str,
                run_id: str | None = None, stage: str | None = None,
                ) -> logging.LoggerAdapter:
    """Bind case/run/stage context onto every subsequent log call without
    repeating it in every format string."""
    extra = {"case_id": case_id}
    if run_id is not None:
        extra["run_id"] = run_id
    if stage is not None:
        extra["stage"] = stage
    return logging.LoggerAdapter(logger, extra)


@dataclass
class _Histogram:
    count: int = 0
    total: float = 0.0
    minimum: float = float("inf")
    maximum: float = float("-inf")

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    def summary(self) -> dict[str, float]:
        if self.count == 0:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": self.count, "mean": self.total / self.count,
            "min": self.minimum, "max": self.maximum,
        }


class MetricsTracker:
    """Process-local in-memory metrics. Real accumulation, not a stub — but
    also not wired to any external metrics backend (Prometheus, StatsD); that
    is a deployment-time concern, named as a follow-on rather than implied
    to exist. Thread-safe: `apps/api` serves requests concurrently."""

    _lock = threading.Lock()
    _inference_times: dict[str, _Histogram] = {}
    _error_counts: dict[str, int] = {}

    @classmethod
    def record_inference_time(cls, model_name: str, duration_ms: float) -> None:
        with cls._lock:
            cls._inference_times.setdefault(model_name, _Histogram()).observe(duration_ms)

    @classmethod
    def increment_error_count(cls, component: str) -> None:
        with cls._lock:
            cls._error_counts[component] = cls._error_counts.get(component, 0) + 1

    @classmethod
    def snapshot(cls) -> dict[str, Any]:
        with cls._lock:
            return {
                "inference_times_ms": {k: v.summary() for k, v in cls._inference_times.items()},
                "error_counts": dict(cls._error_counts),
            }

    @classmethod
    def reset(cls) -> None:
        """Test-only: clear accumulated state between test cases."""
        with cls._lock:
            cls._inference_times.clear()
            cls._error_counts.clear()


def setup_observability() -> None:
    """Kept for backward compatibility with the name this module already
    exposed; delegates to `configure_logging()`."""
    configure_logging()


def build_case_timeline(run: Any) -> list[dict[str, Any]]:
    """
    Turn a `PipelineRun` (or anything exposing `.stages: dict[str, StageResult]`
    and `.run_id`/`.case_id`) into an ordered, human-readable timeline.

    Every field here already existed on `StageResult` — `status`,
    `evidence_mode`, `reason`, `runtime_seconds`, `detail` — this function
    performs no new inference and adds no data the pipeline did not already
    produce. It exists because that data was scattered across a `dict[str,
    StageResult]` with no ordering guarantee and no case/run context attached,
    and answering "why is this case in this state" meant reading pipeline
    source to know which stage ran when.
    """
    # PIPELINE_STAGE_ORDER matches the canonical call graph documented in
    # docs/architecture/CASE_ORCHESTRATION_RECONCILIATION.md §3. A stage name
    # absent from this list is appended at the end rather than dropped, so an
    # unrecognized future stage is still visible, just unordered.
    order = [
        "forcing", "ais_ingest", "netra_detection", "phi_reconstruction",
        "attribution", "validity", "forecast", "decision", "mission", "alerts",
    ]
    stages: dict[str, Any] = getattr(run, "stages", {})
    ordered_names = [n for n in order if n in stages] + \
                    [n for n in stages if n not in order]

    timeline = []
    for name in ordered_names:
        result = stages[name]
        entry = {
            "stage": name,
            "status": result.status.value if hasattr(result.status, "value") else result.status,
            "evidence_mode": (result.evidence_mode.value
                              if getattr(result, "evidence_mode", None) else None),
            "reason": getattr(result, "reason", None),
            "runtime_seconds": getattr(result, "runtime_seconds", None),
            "detail": getattr(result, "detail", {}) or {},
        }
        timeline.append(entry)

    return timeline


def summarize_case_state(run: Any) -> dict[str, Any]:
    """
    One-paragraph-equivalent structured summary of why a case is in its
    current state: the timeline plus the first BLOCKED or terminal
    NOT_YET_PRODUCED stage, which is almost always the answer an operator
    or developer actually wants.
    """
    timeline = build_case_timeline(run)
    first_non_produced = next(
        (e for e in timeline if e["status"] != "produced"), None
    )
    return {
        "run_id": getattr(run, "run_id", None),
        "case_id": getattr(run, "case_id", None),
        "evidence_mode": (run.evidence_mode.value
                          if getattr(run, "evidence_mode", None) else None),
        "n_stages_produced": sum(1 for e in timeline if e["status"] == "produced"),
        "n_stages_total": len(timeline),
        "first_unproduced_stage": (
            {"stage": first_non_produced["stage"],
             "status": first_non_produced["status"],
             "reason": first_non_produced["reason"]}
            if first_non_produced else None
        ),
        "timeline": timeline,
    }
