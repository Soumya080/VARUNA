"""
VARUNA — operational response loop (Workstream A integration point).

Sits at the SAME composition boundary ADR-0013 established for
intelligence: `GoldenCaseWorkflow` produces science, `build_product_case()`
composes the operator view, and THIS runs the operational chain over the
composed result. GoldenCaseWorkflow is not modified to do any of it, so a
failure in alerting can never corrupt a scientific run.

    OperatorCase (current) + OperatorCase (previous)
        -> Event Spine emissions
        -> Material Change Engine
        -> Alert Orchestrator (dedupe/enrich/prioritise/route/deliver)
        -> SMRITI persistence

Determinism: the previous-snapshot store is keyed by case_id and holds the
last composed case. A replay of the same fixture from a clean process
therefore produces exactly the same material changes and the same dedupe
keys.
"""
from __future__ import annotations

from typing import Any

from varuna_alerts.material_change import MaterialChange, evaluate_material_changes


class CaseSnapshotStore:
    """Last-seen composed case per case_id. In-process and deterministic;
    no TTL, no clock dependence."""

    def __init__(self) -> None:
        self._snapshots: dict[str, Any] = {}

    def get(self, case_id: str) -> Any:
        return self._snapshots.get(case_id)

    def put(self, case_id: str, case: Any) -> None:
        self._snapshots[case_id] = case

    def clear(self) -> None:
        self._snapshots.clear()


def _to_case_memory(operator_case: Any, run_id: str | None):
    """Project a composed OperatorCase onto SMRITI's CaseMemory contract.

    Structured fields only, and only fields SMRITI already defines — no new
    memory schema is invented, and nothing scientific is recomputed. SMRITI
    stays advisory: this writes a record, it never reads one back into the
    current case's evidence.
    """
    from varuna_smriti.memory import CaseMemory

    def sec(name: str):
        return getattr(operator_case, name, None)

    def val(name: str):
        s = sec(name)
        return getattr(s, "value", None) if s is not None else None

    det = val("detection")
    attr = val("attribution")
    validity = val("validity")
    sp = getattr(operator_case, "starting_point", None)
    point = getattr(sp, "point", None) if sp is not None else None
    hyps = getattr(getattr(operator_case, "intelligence", None), "hypotheses", None)
    top_class, top_post = None, None
    if hyps is not None:
        items = getattr(hyps, "hypotheses", None) or []
        if items:
            best = max(items, key=lambda h: getattr(h, "posterior", 0.0))
            top_class = getattr(getattr(best, "source_class", None), "value",
                                getattr(best, "source_class", None))
            top_post = getattr(best, "posterior", None)

    v_state = getattr(validity, "state", None) if validity is not None else None
    return CaseMemory(
        case_id=operator_case.case_id,
        centroid_lon=getattr(point, "lon", None),
        centroid_lat=getattr(point, "lat", None),
        area_km2=getattr(det, "area_km2", None) if det is not None else None,
        elongation=getattr(det, "elongation", None) if det is not None else None,
        top_source_class=str(top_class) if top_class is not None else None,
        source_posterior=top_post,
        attribution_state=("produced" if attr is not None else "not_produced"),
        validity_state=(getattr(v_state, "value", v_state) if v_state is not None else None),
        evidence_mode=getattr(getattr(sec("detection"), "evidence_mode", None), "value", None)
        if sec("detection") is not None else None,
        outcome=getattr(getattr(operator_case, "recommendation", None), "value", None),
        run_id=run_id,
        model_versions={k: str(v) for k, v in
                        (getattr(operator_case.provenance, "model_versions", None) or {}).items()},
        provenance_source="varuna.operational_loop",
    )


def run_operational_loop(
    operator_case: Any, *, snapshots: CaseSnapshotStore,
    orchestrator: Any = None, event_spine: Any = None,
    smriti_store: Any = None, run_id: str | None = None,
    window: str = "run",
) -> dict[str, Any]:
    """Execute the operational chain over one composed OperatorCase.

    Returns a summary dict describing what actually happened — never a
    claim of success for a step that did not run.
    """
    case_id = operator_case.case_id
    previous = snapshots.get(case_id)

    # ---- Material Change Engine -------------------------------------
    changes: list[MaterialChange] = evaluate_material_changes(operator_case, previous)

    # ---- Event Spine -------------------------------------------------
    emitted: list[str] = []
    if event_spine is not None:
        for c in changes:
            try:
                event_spine.emit(
                    c.event_type, case_id, actor="material_change_engine",
                    payload={
                        "dimension": c.dimension.value,
                        "previous": c.previous, "current": c.current,
                        "reason": c.reason, "severity": c.severity.value,
                        "severity_basis": c.severity_basis,
                        "evidence_refs": c.evidence_refs,
                        "engine_mode": c.engine_mode,
                        "evidence_mode": c.evidence_mode,
                    },
                )
                emitted.append(c.event_type)
            except Exception:
                continue

    # ---- Alert Orchestrator ------------------------------------------
    alerts = []
    if orchestrator is not None and changes:
        alerts = orchestrator.process_all(changes, window=window)

    # ---- SMRITI (advisory persistence) -------------------------------
    smriti_written = False
    smriti_error = None
    if smriti_store is not None:
        try:
            smriti_store.store_case(_to_case_memory(operator_case, run_id))
            smriti_written = True
        except Exception as exc:
            smriti_error = f"{type(exc).__name__}: {exc}"

    snapshots.put(case_id, operator_case)

    return {
        "case_id": case_id,
        "had_previous_snapshot": previous is not None,
        "material_changes": [c.model_dump(mode="json") for c in changes],
        "n_material_changes": len(changes),
        "events_emitted": emitted,
        "alerts": [a.alert_id for a in alerts],
        "n_alerts": len(alerts),
        "smriti_written": smriti_written,
        "smriti_error": smriti_error,
    }
