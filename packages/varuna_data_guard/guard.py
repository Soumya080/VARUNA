"""
VARUNA GRID — Data Guard.

Validates input artifacts before scientific processing.
Returns ACCEPTED, DEGRADED, or QUARANTINED.
"""
from enum import Enum
from typing import Dict, Any, List, Optional
import numpy as np


class GuardVerdict(str, Enum):
    ACCEPTED = "accepted"
    DEGRADED = "degraded"
    QUARANTINED = "quarantined"


class GuardResult:
    def __init__(self, verdict: GuardVerdict, checks: List[Dict[str, Any]],
                 blocking_reasons: Optional[List[str]] = None):
        self.verdict = verdict
        self.checks = checks
        self.blocking_reasons = blocking_reasons or []


def evaluate_data_guard(
    slick_lons: np.ndarray,
    slick_lats: np.ndarray,
    n_tracks: int,
    obs_time_hours: float,
) -> GuardResult:
    """
    Run data quality checks on scientific input.
    """
    checks = []
    blocking = []

    # Check 1: Slick has enough points
    n_points = len(slick_lons) if slick_lons is not None else 0
    ok = n_points >= 10
    checks.append({"name": "slick_point_count", "passed": ok, "observed": n_points, "threshold": 10})
    if not ok:
        blocking.append(f"Slick has only {n_points} points (need >=10)")

    # Check 2: Slick is within valid geographic bounds
    if n_points > 0:
        lon_ok = np.all((slick_lons >= -180) & (slick_lons <= 180))
        lat_ok = np.all((slick_lats >= -90) & (slick_lats <= 90))
        geo_ok = bool(lon_ok and lat_ok)
    else:
        geo_ok = False
    checks.append({"name": "geographic_bounds", "passed": geo_ok})
    if not geo_ok:
        blocking.append("Slick coordinates out of geographic bounds")

    # Check 3: At least one candidate track
    track_ok = n_tracks >= 1
    checks.append({"name": "candidate_tracks", "passed": track_ok, "observed": n_tracks})

    # Check 4: Observation time is positive.
    #
    # M4 fix (docs/product/HONESTY_LEDGER.md #6): this check was computed
    # and appended to `checks` but never added to `blocking` — a dead check
    # that would have caught M3's negative `obs_time_hours` leak had it
    # been wired to matter. `obs_time_hours` here is this caller's own
    # observation-time convention (a small positive float from the
    # legacy/synthetic ingest path, NOT Phi's PHI_EPOCH-relative coordinate
    # — those are two different things sharing a name; see
    # `ObservationView.phi_time_coordinate_hours`'s docstring), so
    # "positive" genuinely is the right invariant for this call site, and
    # a caller passing something else now actually gets quarantined for it
    # instead of the failure being silently recorded and ignored.
    time_ok = obs_time_hours > 0
    checks.append({"name": "obs_time_positive", "passed": time_ok})
    if not time_ok:
        blocking.append(f"obs_time_hours={obs_time_hours} is not positive")

    if blocking:
        return GuardResult(GuardVerdict.QUARANTINED, checks, blocking)
    elif not track_ok:
        return GuardResult(GuardVerdict.DEGRADED, checks, ["No candidate tracks available"])
    else:
        return GuardResult(GuardVerdict.ACCEPTED, checks)
