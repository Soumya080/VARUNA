"""
VARUNA — Material Change Engine (Workstream A, Phase 2).

Answers ONE question deterministically: *what changed enough that an
operator should care?*

Before this module, `varuna_alerts.materiality.check_materiality()` answered
a narrower question — "is this event type in an allow-list, and does the
validity gate permit alerting" — with no notion of a PREVIOUS state. It
therefore could not distinguish "the case was refreshed" from "the case
actually changed", which is exactly the distinction that stops an operator
being spammed. That function is kept and still runs (it is the gate on
outbound sends); this module sits in front of it and decides whether there
is a material change at all.

Design constraints honoured here:
  * Deterministic. Same (previous, current) pair -> same result, always.
    No clocks, no randomness, no model calls. Replay-safe by construction.
  * No invented numbers. Thresholds are declared constants with a stated
    rationale; nothing is converted into a calibrated probability, and an
    uncalibrated posterior stays uncalibrated.
  * Every change carries previous value, new value, the dimension that
    moved, a human reason, the severity basis, and evidence references.
"""
from __future__ import annotations

import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from varuna_contracts.operator_case import AlertSeverity


class MaterialDimension(StrEnum):
    """The axis along which something changed. Part of the dedupe identity
    (see `varuna_alerts.dedupe_identity`), so these names are stable."""

    DETECTION_PRESENCE = "detection.presence"
    DETECTION_CONFIDENCE = "detection.confidence"
    ORIGIN_POSITION = "origin.position"
    ATTRIBUTION_POSTERIOR = "attribution.posterior"
    VALIDITY_STATE = "validity.state"
    LANDFALL_PREDICTION = "landfall.prediction"
    MISSION_STATE = "mission.state"


# --------------------------------------------------------------------------
# Thresholds. Declared, not tuned — each states WHY it exists. They are
# operator-attention thresholds ("is this worth a human's time"), explicitly
# NOT scientific significance thresholds, and they never alter any value.
# --------------------------------------------------------------------------

#: Absolute change in detection confidence considered operationally material.
#: 0.10 on a 0..1 scale — a tenth of the full range; smaller wobble is noise
#: from the operator's point of view.
CONFIDENCE_DELTA = 0.10

#: Absolute change in attribution posterior considered material. Same
#: rationale as above. Note this is a RELATIVE plausibility in this system,
#: never a calibrated probability — the threshold does not change that.
POSTERIOR_DELTA = 0.10

#: Distance the reconstructed origin must move to matter operationally.
#: 5 km is the order of a search-box edge in this system's own tasking
#: (`AssetTasking.search_box`), so a shift of that size changes where an
#: asset would actually be sent.
ORIGIN_MOVE_KM = 5.0


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class MaterialChange(BaseModel):
    """One operator-relevant change. Carries everything a reviewer needs to
    audit *why* an alert existed, without re-deriving it."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    dimension: MaterialDimension
    event_type: str
    previous: Any = None
    current: Any = None
    reason: str
    severity: AlertSeverity
    severity_basis: str
    evidence_refs: list[str] = Field(default_factory=list)
    engine_mode: str | None = None
    evidence_mode: str | None = None


# --------------------------------------------------------------------------
# Severity. Derived from real state, with an explainable basis string on
# every branch. CRITICAL is reachable ONLY on evidence this system actually
# computes (a validity gate that blocks action while a landfall is
# predicted) — never from a model score, because no score here is calibrated.
# --------------------------------------------------------------------------

def _severity_for(dimension: MaterialDimension, *, validity_state: str | None,
                  has_landfall: bool, blocks_action: bool) -> tuple[AlertSeverity, str]:
    if dimension is MaterialDimension.LANDFALL_PREDICTION:
        if blocks_action:
            return (AlertSeverity.CRITICAL,
                    "a landfall is predicted while the validity gate blocks operational "
                    "action — shoreline impact is expected and no response is authorised")
        return (AlertSeverity.HIGH,
                "a landfall is predicted for this case (shoreline impact expected)")

    if dimension is MaterialDimension.VALIDITY_STATE:
        if validity_state in ("restricted", "inconclusive"):
            return (AlertSeverity.HIGH,
                    f"validity degraded to {validity_state!r}, which withdraws operational "
                    "authorisation for this case")
        return (AlertSeverity.MEDIUM, f"validity state changed to {validity_state!r}")

    if dimension is MaterialDimension.MISSION_STATE:
        return (AlertSeverity.HIGH,
                "mission state changed — a physical asset commitment is involved")

    if dimension is MaterialDimension.DETECTION_PRESENCE:
        return (AlertSeverity.HIGH,
                "a new oil-slick detection was produced for this case")

    if dimension in (MaterialDimension.DETECTION_CONFIDENCE,
                     MaterialDimension.ATTRIBUTION_POSTERIOR):
        return (AlertSeverity.MEDIUM,
                f"{dimension.value} moved by more than the operator-attention threshold; "
                "the underlying value is uncalibrated and is reported as-is")

    if dimension is MaterialDimension.ORIGIN_POSITION:
        return (AlertSeverity.MEDIUM,
                f"reconstructed origin moved more than {ORIGIN_MOVE_KM} km, which changes "
                "where an asset would be tasked")

    return (AlertSeverity.LOW, "state changed")


def _get(obj: Any, *path: str) -> Any:
    cur = obj
    for key in path:
        if cur is None:
            return None
        cur = cur.get(key) if isinstance(cur, dict) else getattr(cur, key, None)
    return cur


def _section(case: Any, name: str) -> Any:
    return case.get(name) if isinstance(case, dict) else getattr(case, name, None)


def _evidence_refs(section: Any, *extra: Any) -> list[str]:
    """Canonical, resolvable evidence references for a section.

    Prefers `envelope.artifact_id` — the id PRAMAN and the evidence lineage
    actually use, so a UI can follow an alert back to the artifact that
    caused it — then any parent artifact ids, then domain ids passed by the
    caller (slick_id, forecast_id, ...).

    Origin, attribution and validity previously produced `evidence_refs=[]`,
    which are the three dimensions an operator most wants to drill into.
    """
    refs: list[str] = []
    env = _get(section, "value", "envelope")
    art = _get(env, "artifact_id")
    if art:
        refs.append(str(art))
    for parent in (_get(env, "parent_artifact_ids") or []):
        if parent and str(parent) not in refs:
            refs.append(str(parent))
    for e in extra:
        if e and str(e) not in refs:
            refs.append(str(e))
    return refs


def _produced(section: Any) -> bool:
    st = _get(section, "status")
    return (st.value if hasattr(st, "value") else st) == "produced"


def evaluate_material_changes(
    current_case: Any, previous_case: Any = None,
) -> list[MaterialChange]:
    """Compare two OperatorCase snapshots and return only the changes an
    operator should be told about.

    `previous_case=None` means "first time this case has been seen", which
    is itself material for the things that exist — but only for things that
    genuinely exist. A first sighting with no detection produces no change,
    which is what keeps CASE-OOD silent.
    """
    case_id = _get(current_case, "case_id") or "unknown"
    engine_mode = _get(current_case, "system_status", "engine_mode")

    validity_sec = _section(current_case, "validity")
    validity_state = _get(validity_sec, "value", "state")
    if hasattr(validity_state, "value"):
        validity_state = validity_state.value
    blocks_action = validity_state not in ("valid", "degraded")

    forecast_sec = _section(current_case, "forecast")
    landfalls = _get(forecast_sec, "value", "landfalls") or []
    # M5 belt-and-braces (docs/product/HONESTY_LEDGER.md #7): the root
    # cause was a fixture constructing a `LandfallPrediction` to represent
    # "there is no landfall" (fixed at the source — see
    # replay_fixtures._india_forecast), but an alert whose reason names no
    # concrete location is a defect regardless of which producer causes it.
    # A landfall entry only counts here if it names a real place.
    landfalls = [lf for lf in landfalls if str(_get(lf, "location_name") or "").strip()]
    has_landfall = len(landfalls) > 0

    changes: list[MaterialChange] = []

    def add(dim: MaterialDimension, event_type: str, prev: Any, cur: Any,
            reason: str, refs: list[str], ev_mode: Any = None) -> None:
        sev, basis = _severity_for(dim, validity_state=validity_state,
                                   has_landfall=has_landfall, blocks_action=blocks_action)
        mode = ev_mode.value if hasattr(ev_mode, "value") else ev_mode
        changes.append(MaterialChange(
            case_id=case_id, dimension=dim, event_type=event_type,
            previous=prev, current=cur, reason=reason,
            severity=sev, severity_basis=basis, evidence_refs=refs,
            engine_mode=engine_mode, evidence_mode=mode,
        ))

    # ---- detection ------------------------------------------------------
    det = _section(current_case, "detection")
    prev_det = _section(previous_case, "detection") if previous_case is not None else None
    if _produced(det):
        slick_id = _get(det, "value", "slick_id")
        conf = _get(det, "value", "confidence")
        if not _produced(prev_det):
            add(MaterialDimension.DETECTION_PRESENCE, "detection.created",
                None, {"slick_id": slick_id, "confidence": conf},
                f"first detection produced for this case (slick {slick_id})",
                _evidence_refs(det, slick_id), _get(det, "evidence_mode"))
        else:
            prev_conf = _get(prev_det, "value", "confidence")
            if (conf is not None and prev_conf is not None
                    and abs(conf - prev_conf) >= CONFIDENCE_DELTA):
                add(MaterialDimension.DETECTION_CONFIDENCE, "detection.updated",
                    prev_conf, conf,
                    f"detection confidence moved {prev_conf:.2f} -> {conf:.2f} "
                    f"(>= {CONFIDENCE_DELTA} operator-attention threshold)",
                    _evidence_refs(det, slick_id), _get(det, "evidence_mode"))

    # ---- origin ---------------------------------------------------------
    sp = _section(current_case, "starting_point")
    prev_sp = _section(previous_case, "starting_point") if previous_case is not None else None
    sp_status = _get(sp, "status")
    sp_status = sp_status.value if hasattr(sp_status, "value") else sp_status
    if sp_status == "STARTING_POINT_AVAILABLE":
        lon, lat = _get(sp, "point", "lon"), _get(sp, "point", "lat")
        plon, plat = _get(prev_sp, "point", "lon"), _get(prev_sp, "point", "lat")
        if plon is not None and plat is not None and lon is not None:
            moved = _haversine_km(plon, plat, lon, lat)
            if moved >= ORIGIN_MOVE_KM:
                add(MaterialDimension.ORIGIN_POSITION, "origin.updated",
                    {"lon": plon, "lat": plat}, {"lon": lon, "lat": lat},
                    f"reconstructed origin moved {moved:.1f} km "
                    f"(>= {ORIGIN_MOVE_KM} km threshold)",
                    _evidence_refs(_section(current_case, "origin")),
                    _get(sp, "evidence_mode"))

    # ---- attribution ----------------------------------------------------
    attr = _section(current_case, "attribution")
    prev_attr = _section(previous_case, "attribution") if previous_case is not None else None
    if _produced(attr):
        top = _get(attr, "value", "top_posterior")
        prev_top = _get(prev_attr, "value", "top_posterior") if _produced(prev_attr) else None
        if prev_top is None:
            add(MaterialDimension.ATTRIBUTION_POSTERIOR, "attribution.generated",
                None, top,
                f"attribution produced (top relative posterior {top}); value is "
                "uncalibrated and reported as-is",
                _evidence_refs(attr), _get(attr, "evidence_mode"))
        elif top is not None and abs(top - prev_top) >= POSTERIOR_DELTA:
            add(MaterialDimension.ATTRIBUTION_POSTERIOR, "attribution.generated",
                prev_top, top,
                f"attribution posterior moved {prev_top:.2f} -> {top:.2f} "
                f"(>= {POSTERIOR_DELTA} threshold); uncalibrated value",
                _evidence_refs(attr), _get(attr, "evidence_mode"))

    # ---- validity -------------------------------------------------------
    prev_validity = None
    if previous_case is not None:
        prev_validity = _get(_section(previous_case, "validity"), "value", "state")
        if hasattr(prev_validity, "value"):
            prev_validity = prev_validity.value
    if validity_state is not None and validity_state != prev_validity:
        add(MaterialDimension.VALIDITY_STATE, "validity.changed",
            prev_validity, validity_state,
            f"validity gate state {prev_validity!r} -> {validity_state!r}",
            _evidence_refs(validity_sec), _get(validity_sec, "evidence_mode"))

    # ---- landfall -------------------------------------------------------
    prev_landfalls = (_get(_section(previous_case, "forecast"), "value", "landfalls") or []
                      if previous_case is not None else [])
    if has_landfall and len(landfalls) != len(prev_landfalls):
        names = [_get(lf, "location_name") for lf in landfalls]
        add(MaterialDimension.LANDFALL_PREDICTION, "landfall.predicted",
            len(prev_landfalls), len(landfalls),
            f"forecast predicts landfall at {', '.join(str(n) for n in names)}",
            _evidence_refs(forecast_sec, _get(forecast_sec, "value", "forecast_id")),
            _get(forecast_sec, "evidence_mode"))

    # ---- mission --------------------------------------------------------
    mission_sec = _section(current_case, "mission")
    missions = _get(mission_sec, "value") or []
    prev_missions = (_get(_section(previous_case, "mission"), "value") or []
                     if previous_case is not None else [])
    prev_states = {_get(m, "mission_id"): _get(m, "state") for m in prev_missions}
    for m in missions:
        mid, state = _get(m, "mission_id"), _get(m, "state")
        state = state.value if hasattr(state, "value") else state
        prev_state = prev_states.get(mid)
        prev_state = prev_state.value if hasattr(prev_state, "value") else prev_state
        if mid in prev_states and state != prev_state:
            add(MaterialDimension.MISSION_STATE, "mission.assigned",
                prev_state, state,
                f"mission {mid} moved {prev_state!r} -> {state!r}",
                [str(mid)], _get(mission_sec, "evidence_mode"))

    return changes
