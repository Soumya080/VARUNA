"""
Alert severity — structural only. See `AlertSeverity`'s own docstring
(varuna_contracts.operator_case) for why CRITICAL is never assigned here.

`infer_severity()` reflects two facts the alert pipeline already computes —
was the send suppressed (materiality/freshness/dedupe), did it reach a
simulated channel — and invents nothing beyond them. There is no existing
repository policy (checked: materiality.py, freshness.py, role_router.py,
templates.py) that scores how urgent a real spill event is, so this
function does not attempt to. See
reports/mission/ABHIYAN_MISSION_ALERTS_REPORT.md, "Alert severity policy gap".
"""
from __future__ import annotations

from varuna_contracts.operator_case import AlertSeverity

__all__ = ["infer_severity"]


def infer_severity(*, suppressed: bool, is_simulated: bool) -> AlertSeverity:
    """
    suppressed=True   -> BLOCKED   (materiality/freshness/dedupe withheld the send —
                                     mirrors StageStatus.BLOCKED's naming, not a new idea)
    is_simulated=True -> WARNING   (reached only a demo/mock channel, not a live one)
    otherwise         -> INFO      (a real send actually happened)

    CRITICAL is intentionally unreachable. Assigning it would require an
    urgency policy (spill volume, shoreline ETA, asset proximity, ...) that
    does not exist anywhere in this codebase; fabricating one here would be
    exactly the kind of invented safety-critical rule this task prohibits.
    """
    if suppressed:
        return AlertSeverity.BLOCKED
    if is_simulated:
        return AlertSeverity.WARNING
    return AlertSeverity.INFO
