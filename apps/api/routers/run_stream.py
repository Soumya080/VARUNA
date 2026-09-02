"""
VARUNA — real-execution stage stream (Server-Sent Events).

Lets an operator WATCH the canonical chain execute instead of only seeing
its finished output. No Kafka/Celery/Redis: this is a plain SSE generator
over the same synchronous canonical path everything else uses
(GoldenCaseWorkflow -> build_product_case -> OperatorCase).

Honesty of `elapsed_ms`, stated precisely because "do not fake progress"
is a hard requirement:

* `elapsed_ms` is ALWAYS real monotonic wall-clock measured from the start
  of this run, at the moment that stage's result became observable to this
  endpoint. It is never simulated and no artificial delay is ever inserted.
* `stage_runtime_ms` is the stage's OWN recorded `runtime_seconds` when the
  producer recorded one, and `null` when it did not. Replay fixtures are
  canned data and record no per-stage runtime, so this is `null` for them —
  reported honestly rather than back-filled with a plausible number.
* Because `run_replay_case()` is a single synchronous call that returns a
  fully-populated run, the pipeline stages inside it genuinely all become
  observable at the same instant. Their `elapsed_ms` values therefore
  cluster, and that is the truth about how a replay executes — the stream
  does not spread them out to look more impressive.

Stage statuses come from the real `StageResult.status` / section
`ProducerStatus`, never from a hardcoded success list.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from apps.api.dependencies import get_golden_case_workflow, get_replay_smriti_store
from varuna_domain.replay_fixtures import FIXTURE_NAMES

router = APIRouter(prefix="/v1/run", tags=["run"])

# Operator-facing stage vocabulary -> the pipeline stage that actually
# produces it. `None` means the stage is derived from the composed
# OperatorCase rather than from a PipelineRun stage.
_PIPELINE_STAGE = {
    "DATA": "forcing",
    "NETRA": "netra_detection",
    "DETECTION_EVIDENCE": None,
    "STARTING_POINT": None,
    "PRATIVARTAN": "phi_reconstruction",
    "PRAVAAH": "forecast",
    "CHHAYA": None,
    "NYAYA": "attribution",
    "VALIDITY": "validity",
    "NEXT_BEST_ACTION": None,
    "ALERT": "alerts",
    "MISSION": "mission",
    "PRAMAN": None,
}

STAGE_ORDER = list(_PIPELINE_STAGE.keys())


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _stage_event(name: str, status: str, elapsed_ms: float, *,
                 reason: str | None = None, case_id: str | None = None,
                 run_id: str | None = None, stage_runtime_ms: float | None = None,
                 detail: dict | None = None) -> dict:
    return {
        "type": "stage",
        "stage": name,
        "status": status,
        "elapsed_ms": round(elapsed_ms, 1),
        "stage_runtime_ms": stage_runtime_ms,
        "reason": reason,
        "case_id": case_id,
        "run_id": run_id,
        "detail": detail or {},
    }


def _derived_status(section: Any) -> tuple[str, str | None]:
    """Map a composed OperatorCase section onto a stage status, using the
    section's real ProducerStatus — never assuming success."""
    if section is None:
        return "not_yet_produced", "section absent from the operator case"
    status = getattr(section, "status", None)
    reason = getattr(section, "reason", None)
    return (status.value if hasattr(status, "value") else str(status)), reason


@router.get("/fixtures")
def list_runnable_fixtures():
    return {"fixtures": list(FIXTURE_NAMES)}


@router.get("/{fixture_name}/stream")
def stream_run(
    fixture_name: str,
    workflow=Depends(get_golden_case_workflow),
    smriti=Depends(get_replay_smriti_store),
):
    if fixture_name not in FIXTURE_NAMES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown fixture {fixture_name!r}. Known: {list(FIXTURE_NAMES)}",
        )

    def generate() -> Iterator[str]:
        from varuna_integration.product_case import build_product_case

        t0 = time.perf_counter()

        def ms() -> float:
            return (time.perf_counter() - t0) * 1000.0

        case_id = f"REPLAY-{fixture_name}"
        yield _sse({"type": "run_started", "fixture": fixture_name,
                    "case_id": case_id, "stages": STAGE_ORDER,
                    "elapsed_ms": round(ms(), 1)})

        # ---- execute the canonical path (genuinely, once) ---------------
        try:
            result = workflow.run_replay_case(case_id, fixture_name, force=True)
        except Exception as exc:  # a crash in the engine itself
            yield _sse({"type": "run_failed", "elapsed_ms": round(ms(), 1),
                        "error": f"{type(exc).__name__}: {exc}"})
            return
        t_run = ms()
        run_id = getattr(result.run, "run_id", None)

        try:
            operator_case = build_product_case(result, workflow, smriti=smriti)
        except Exception as exc:
            yield _sse({"type": "run_failed", "elapsed_ms": round(ms(), 1),
                        "error": f"compose failed: {type(exc).__name__}: {exc}"})
            return
        t_compose = ms()

        stages = getattr(result.run, "stages", {}) or {}
        intel = operator_case.intelligence

        for name in STAGE_ORDER:
            pipeline_stage = _PIPELINE_STAGE[name]

            if pipeline_stage is not None:
                sr = stages.get(pipeline_stage)
                if sr is None:
                    status, reason, runtime = "not_yet_produced", \
                        f"pipeline stage {pipeline_stage!r} did not run", None
                else:
                    raw = getattr(sr, "status", None)
                    status = raw.value if hasattr(raw, "value") else str(raw)
                    reason = getattr(sr, "reason", None)
                    rt = getattr(sr, "runtime_seconds", None)
                    runtime = round(rt * 1000.0, 1) if rt else None
                yield _sse(_stage_event(name, status, t_run, reason=reason,
                                        case_id=case_id, run_id=run_id,
                                        stage_runtime_ms=runtime))
                continue

            # ---- stages derived from the composed OperatorCase ----------
            if name == "DETECTION_EVIDENCE":
                status, reason = _derived_status(operator_case.detection)
                detail = {}
                if operator_case.detection.value is not None:
                    dv = operator_case.detection.value
                    detail = {"classification": getattr(dv, "classification", None),
                              "confidence": getattr(dv, "confidence", None)}
                yield _sse(_stage_event(name, status, t_run, reason=reason,
                                        case_id=case_id, run_id=run_id, detail=detail))
            elif name == "STARTING_POINT":
                sp = operator_case.starting_point
                pt = sp.point
                yield _sse(_stage_event(
                    name,
                    "produced" if sp.status.value == "STARTING_POINT_AVAILABLE"
                    else "blocked",
                    t_compose, reason=sp.reason, case_id=case_id, run_id=run_id,
                    detail={"contract_status": sp.status.value,
                            "source": sp.source.value,
                            "land_classification": sp.land_classification.value,
                            "lon": pt.lon if pt else None,
                            "lat": pt.lat if pt else None}))
            elif name == "CHHAYA":
                has = intel.hypotheses is not None
                yield _sse(_stage_event(
                    name, "produced" if has else "not_yet_produced", t_compose,
                    reason=None if has else (intel.reason or "no hypotheses composed"),
                    case_id=case_id, run_id=run_id))
            elif name == "NEXT_BEST_ACTION":
                has = intel.next_best_action is not None
                yield _sse(_stage_event(
                    name, "produced" if has else "not_yet_produced", t_compose,
                    reason=None if has else (intel.reason or "no next-best-action composed"),
                    case_id=case_id, run_id=run_id))
            elif name == "PRAMAN":
                ids = operator_case.provenance.artifact_ids or []
                yield _sse(_stage_event(
                    name, "produced" if ids else "not_yet_produced", t_compose,
                    reason=None if ids else "no artifacts registered for this case",
                    case_id=case_id, run_id=run_id,
                    detail={"n_artifacts": len(ids)}))

        yield _sse({"type": "run_complete", "case_id": case_id, "run_id": run_id,
                    "elapsed_ms": round(ms(), 1),
                    "workflow_ms": round(t_run, 1),
                    "compose_ms": round(t_compose - t_run, 1),
                    "recommendation": operator_case.recommendation.value,
                    "engine_mode": operator_case.system_status.engine_mode})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
