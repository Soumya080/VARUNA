"""
VARUNA GRID — Behavioural emission prior calculation.

Track 2 Phase 3 audit of the three sub-scores below (previously all hardcoded
`return 0.1  # mock for M2`):

  compute_speed_anomaly   -> A. IMPLEMENTABLE NOW
  compute_loiter_score    -> A. IMPLEMENTABLE NOW
  compute_night_proximity -> A. IMPLEMENTABLE NOW

All three are implementable now because a real specification already exists
in the codebase for each, and the inputs each specification needs are
already present on `VesselTrack`/`PhiField`:

  - speed anomaly: `varuna_data_eng/preprocessing/ais_cleaner.py` already
    defines "> 50.0 knots" as PHYSICALLY_IMPLAUSIBLE_SOG. That threshold
    predates this change and is reused here verbatim, not invented.
  - loiter_score / night_proximity: `varuna_contracts/schemas.py`'s
    `VesselScore` fields carry the specification in-line as a comment —
    "time <3kt within 5nm of a point" and "near origin field 00:00-05:00
    local" respectively. Both are implemented exactly as specified there.

None of this touches NYAYA's Bayesian mathematics (posterior.py,
likelihoods.py, corridor.py) — it only replaces three previously-fabricated
*inputs* to the existing, unchanged prior-combination formula in
compute_prior() below.
"""
import numpy as np

from varuna_contracts.decision import PriorContribution
from varuna_contracts.phi import PhiField
from varuna_contracts.schemas import GeoPoint, VesselTrack
from varuna_geospatial.utils import haversine_km_vec

TYPE_WEIGHTS = {
    "tanker": 1.5,
    "cargo": 1.2,
    "fishing": 0.8,
    "unknown": 1.0
}

# Same constant as AISCleaner.clean()'s PHYSICALLY_IMPLAUSIBLE_SOG check
# (packages/varuna_data_eng/preprocessing/ais_cleaner.py). AISCleaner also
# exempts high-speed craft (AIS type codes 40-49); VesselType on the locked
# schema has no high-speed-craft member, so that exemption cannot apply to
# any value this function can see — every track is evaluated against the
# same cap.
SPEED_IMPLAUSIBLE_KNOTS = 50.0

# VesselScore.loiter_score's existing specification (schemas.py): "time
# <3kt within 5nm of a point".
LOITER_SPEED_KNOTS = 3.0
LOITER_RADIUS_KM = 5.0 * 1.852  # 5 nautical miles

# VesselScore.night_proximity's existing specification: "00:00-05:00 local".
NIGHT_START_HOUR = 0.0
NIGHT_END_HOUR = 5.0


def compute_speed_anomaly(track: VesselTrack) -> float:
    """
    Fraction of the track's points reporting SOG above the same physical-
    implausibility threshold AISCleaner already applies at ingestion
    (SPEED_IMPLAUSIBLE_KNOTS = 50.0). A vessel whose transponder repeatedly
    reports implausible speed is itself an anomaly worth surfacing to the
    prior, independent of whether AISCleaner already flagged the raw
    record — `VesselTrack` (the locked schema NYAYA consumes) does not
    carry AISCleaner's `quality_flags` through `raw_to_locked()`, so this
    is computed directly from `sog_knots` rather than assumed to already
    be reflected upstream.

    Returns 0.0 if the track has no points with a recorded SOG at all —
    never a fabricated middle value for "we don't know".
    """
    sog_values = [p.sog_knots for p in track.points if p.sog_knots is not None]
    if not sog_values:
        return 0.0
    n_anomalous = sum(1 for s in sog_values if s > SPEED_IMPLAUSIBLE_KNOTS)
    return min(1.0, n_anomalous / len(sog_values))


def compute_loiter_score(track: VesselTrack, phi: PhiField) -> float:
    """
    Per VesselScore.loiter_score's existing specification: "time <3kt
    within 5nm of a point". The reference point is `phi.primary_mode`'s
    centroid when PRATIVARTAN has computed one; today `phi.spatial_modes`
    is always `[]` (see phi_builder.py), so this falls back to
    `phi.bbox.center` — a real, already-computed value from the actual
    ensemble output, not a new assumption.

    Returns the fraction of track points simultaneously below
    LOITER_SPEED_KNOTS and within LOITER_RADIUS_KM of that point, among
    points with a recorded SOG. 0.0 if none.
    """
    ref_point = phi.primary_mode.centroid if phi.primary_mode is not None else phi.bbox.center

    usable = [p for p in track.points if p.sog_knots is not None]
    if not usable:
        return 0.0

    lons = np.array([p.lon for p in usable])
    lats = np.array([p.lat for p in usable])
    dist_km = haversine_km_vec(lons, lats, ref_point.lon, ref_point.lat)

    n_loitering = 0
    for p, d in zip(usable, dist_km):
        sog = p.sog_knots
        if sog is not None and sog < LOITER_SPEED_KNOTS and d <= LOITER_RADIUS_KM:
            n_loitering += 1
    return min(1.0, n_loitering / len(usable))


def compute_night_proximity(track: VesselTrack, phi: PhiField) -> float:
    """
    Per VesselScore.night_proximity's existing specification: "near origin
    field 00:00-05:00 local".

    "Near origin field" is evaluated as `phi.bbox.contains(point)` — the
    field's own already-defined bounding box and containment method,
    introducing no new spatial threshold beyond what the schema already
    provides (unlike loiter_score, no radius is specified in the
    docstring, so reusing the field's own bbox avoids inventing one).

    "Local" time is the standard longitude/15-degrees solar-time
    approximation (1 hour of offset per 15 degrees of longitude) — this
    project has no timezone database dependency, and this approximation is
    a well-established convention, not one invented for this function.

    Returns the fraction of track points meeting both conditions. 0.0 if
    the track has no points.
    """
    if not track.points:
        return 0.0

    n_night = 0
    for p in track.points:
        local_hour = (p.timestamp.hour + p.lon / 15.0) % 24.0
        in_night_window = NIGHT_START_HOUR <= local_hour < NIGHT_END_HOUR
        if in_night_window and phi.bbox.contains(GeoPoint(lon=p.lon, lat=p.lat)):
            n_night += 1
    return min(1.0, n_night / len(track.points))


def compute_prior(track: VesselTrack, phi: PhiField) -> PriorContribution:
    gap_score = min(1.0, track.total_gap_minutes / (24 * 60))
    speed_anomaly = compute_speed_anomaly(track)
    loiter_score = compute_loiter_score(track, phi)
    night_proximity = compute_night_proximity(track, phi)

    # Safe default if vessel_type is an Enum or string
    v_type = getattr(track.vessel_type, 'value', str(track.vessel_type)).lower() if track.vessel_type else "unknown"
    type_weight = TYPE_WEIGHTS.get(v_type, 1.0)

    combined = (
        1.0
        + 0.3 * gap_score
        + 0.2 * speed_anomaly
        + 0.2 * loiter_score
        + 0.1 * night_proximity
    ) * type_weight

    return PriorContribution(
        gap_score=gap_score,
        speed_anomaly=speed_anomaly,
        loiter_score=loiter_score,
        night_proximity=night_proximity,
        type_weight=type_weight,
        combined=combined,
        weights_version="hand_tuned_v1",
    )
