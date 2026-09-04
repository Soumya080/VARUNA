"""
Phase 12 - PipelineRun -> Case metadata, so the OperatorCase read projection
can serialize real producer output.

`apps/api/operator_case_view.py` is a pure projection: it reads
`case.metadata[...]` and serializes whatever typed contract it finds there. It
deliberately computes nothing. That design only pays off if something actually
writes the producers' outputs onto the case - which is what this module does.

Each section is written as `{"value": <contract dump>, "evidence_mode": <mode>,
"status": <stage status>, "reason": <why not, if absent>}` so the projection can
report provenance honestly instead of assuming it. Before this, the detection
section hardcoded `EvidenceMode.REAL` for any detection it found, which would
have relabelled a simulated placeholder as real the moment NETRA was wired in -
the exact provenance upgrade ADR-0006 forbids.

Nothing here recomputes a value. Every number written is the one its producer
returned.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from varuna_integration.stage import StageResult, StageStatus

# stage name in PipelineRun  ->  case.metadata key the projection reads
STAGE_TO_METADATA_KEY = {
    "netra_detection": "detection",
    "phi_reconstruction": "phi",
    "attribution": "attribution",
    "validity": "gate_result",
    "forecast": "forecast",
    "decision": "decision",
    "mission": "mission",
    "alerts": "alerts",
    "ais_ingest": "ais",
    "forcing": "forcing",
}


def _dump(value: Any) -> Any:
    """Serialize a producer's output without altering it."""
    if value is None:
        return None
    if isinstance(value, list):
        return [_dump(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__") and not isinstance(value, (str, int, float, bool)):
        return {k: _dump(v) for k, v in vars(value).items()
                if not k.startswith("_") and _jsonable(v)}
    return value


def _jsonable(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool, type(None), list, dict)) or hasattr(v, "model_dump")


def section_payload(result: StageResult) -> dict[str, Any]:
    """One stage -> the envelope the projection reads.

    `evidence_mode` is carried through verbatim from the stage. It is never
    defaulted to REAL: a section with no mode reports `None` (honestly unknown),
    which is different from claiming real provenance.
    """
    return {
        "status": result.status.value,
        "evidence_mode": result.evidence_mode.value if result.evidence_mode else None,
        "reason": result.reason,
        "runtime_seconds": result.runtime_seconds,
        "detail": result.detail,
        "value": _dump(result.value) if result.status is StageStatus.PRODUCED else None,
    }


def apply_run_to_case(case, run) -> None:
    """Write every stage of a `PipelineRun` onto a `Case`'s metadata.

    Mutates `case.metadata` only. The caller is responsible for persisting the
    case; nothing here touches a repository, a file, or a raw artifact.
    """
    case.metadata["pipeline_run"] = {
        "run_id": run.run_id,
        "run_class": run.config.run_class,
        "scientific_result": run.config.is_scientific,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_seconds": run.total_seconds,
        "evidence_mode": run.evidence_mode.value if run.evidence_mode else None,
        "blocked_at": run.blocked_at,
    }
    # Lineage. `ProvenanceView` is built by the API projection from the PRAMAN
    # artifact registry, which this pipeline does not write to - so without this
    # block an operator case produced here ships an EMPTY provenance section
    # even though the producers each know their own version and source. Collect
    # what the stages actually reported; a stage that produced nothing
    # contributes nothing rather than a placeholder.
    model_versions: dict[str, str] = {}
    source_ids: set[str] = set()
    for stage_name, result in run.stages.items():
        detail = result.detail or {}
        version = detail.get("model_version")
        if version:
            model_versions[stage_name] = str(version)
        source = detail.get("source_id")
        if source:
            source_ids.add(str(source))
    case.metadata["pipeline_provenance"] = {
        "model_versions": model_versions,
        "source_ids": sorted(source_ids),
        # Not the same claim as model_version: this records HOW the inputs were
        # prepared, which is what would have made the MC20 domain gap visible.
        "processing_versions": {},
    }

    for stage_name, result in run.stages.items():
        key = STAGE_TO_METADATA_KEY.get(stage_name)
        if key is None:
            continue
        payload = section_payload(result)
        case.metadata[f"{key}_section"] = payload

        # The pre-existing projection reads bare `phi` / `attribution` /
        # `gate_result` keys directly (they predate this bridge). Keep writing
        # those in the original shape so nothing that already worked breaks -
        # but only when the stage genuinely produced a value.
        if key in ("phi", "attribution", "gate_result") and payload["value"] is not None:
            case.metadata[key] = payload["value"]

    # The detection stage carries the slick geometry the rest of the case is
    # built on. The projection's `detection` key expects a single SlickDetection,
    # not a list - write the first and record how many there were.
    det = run.stages.get("netra_detection")
    if det is not None and det.status is StageStatus.PRODUCED and det.value:
        case.metadata["detection"] = _dump(det.value[0])
        case.metadata["detection_section"]["n_detections"] = len(det.value)

    _write_input_block(case, run)


def _write_input_block(case, run) -> None:
    """Populate the `input` key the observation/AIS sections read.

    `CaseWorkflow.ingest()` writes this when a case is created from
    already-extracted slick points. A pipeline-driven case never calls ingest,
    so without this the operator view reports "no observation" and "no AIS" for
    a case that demonstrably has both.

    Everything written here is a value some stage actually produced: the slick
    points are the ones the reconstruction used, the tracks are the ones NYAYA
    scored, and the observation time is the detection's own. Nothing is
    synthesized to fill the block - if a stage produced nothing, its part of the
    block is simply omitted and the section keeps reporting NOT_YET_PRODUCED.
    """
    det = run.stages.get("netra_detection")
    ais = run.stages.get("ais_ingest")
    phi = run.stages.get("phi_reconstruction")

    has_points = bool(getattr(run, "slick_points", ()) and len(run.slick_points) == 2)
    has_tracks = ais is not None and ais.status is StageStatus.PRODUCED and ais.value
    if not has_points and not has_tracks:
        return

    # `ObservationView.obs_time_hours` is a required float. Take it from the
    # reconstruction if it ran, else derive it from the detection's own
    # observation time. If neither exists there is no honest value to write, so
    # the block is skipped entirely and the section keeps saying NOT_YET_PRODUCED
    # rather than being filled with a placeholder.
    # M3 fix (docs/product/HONESTY_LEDGER.md #5): `obs_time_hours` here is
    # Phi's internal coordinate (hours since PHI_EPOCH) — kept as-is for
    # every existing internal consumer (Phi, NYAYA, the sensitivity sweep,
    # ...), all of which genuinely need that coordinate, not a wall-clock
    # time. What was wrong is showing this number to an OPERATOR as if it
    # were an elapsed-hours field (see ObservationView.phi_time_coordinate_hours's
    # docstring). `observation_time` below carries the real wall-clock time
    # this block already has in hand at every branch — it just wasn't being
    # written anywhere before.
    obs_time_hours = None
    observation_time = None
    if phi is not None and phi.detail.get("obs_time_hours") is not None:
        obs_time_hours = float(phi.detail["obs_time_hours"])
        if det is not None and det.status is StageStatus.PRODUCED and det.value:
            observation_time = det.value[0].observation_time
    elif det is not None and det.status is StageStatus.PRODUCED and det.value:
        from varuna_prativartan.cube_field import PHI_EPOCH

        observation_time = det.value[0].observation_time
        obs_time_hours = (
            observation_time - PHI_EPOCH
        ).total_seconds() / 3600.0
    elif has_tracks and ais.detail.get("t_sar"):
        # No slick was detected, but real AIS WAS ingested. Falling through here
        # would make the operator view say "no AIS tracks were ingested" for a
        # case that has five real ones - reporting absence of evidence that was
        # actually collected. The event's own SAR acquisition time is a real
        # observation time, so use it rather than dropping the block.
        from varuna_prativartan.cube_field import PHI_EPOCH

        t_sar = datetime.fromisoformat(ais.detail["t_sar"])
        if t_sar.tzinfo is None:
            t_sar = t_sar.replace(tzinfo=timezone.utc)
        observation_time = t_sar
        obs_time_hours = (t_sar - PHI_EPOCH).total_seconds() / 3600.0
    if obs_time_hours is None:
        return

    block: dict[str, Any] = {"obs_time_hours": obs_time_hours}
    if observation_time is not None:
        block["observation_time"] = observation_time.isoformat()
    if has_points:
        lons, lats = run.slick_points
        block["slick_lons"] = [float(x) for x in lons]
        block["slick_lats"] = [float(y) for y in lats]
    else:
        block["slick_lons"] = []
        block["slick_lats"] = []
    block["tracks"] = [_dump(t) for t in ais.value] if has_tracks else []
    case.metadata["input"] = block
