"""
VARUNA — deterministic starting-point contract.

The forecast/back-trajectory chain needs ONE unambiguous answer to "where
did this spill start?", and until now the product had no explicit contract
for it: the frontend inferred it from `PhiField.centroid`, a field that
does not exist (PhiField carries `bbox`/`spatial_modes`/`diagnostics`, never
a centroid), so a fully-produced origin stage rendered as
"RECONSTRUCTED ORIGIN — not produced".

This module makes the answer explicit, machine-readable, and impossible to
fabricate. It NEVER invents coordinates: every returned point is copied
from an already-validated upstream evidence object, and anything that
cannot be sourced that way is returned as UNAVAILABLE/INVALID with a named
reason rather than a plausible-looking default.

Land classification, deliberately honest: this repository ships no
offline land/coastline mask (geopandas 1.x removed its bundled
Natural Earth dataset; `varuna_pravaah.coastline.check_landfall` is an
India-specific latitude heuristic — `lat > 21 -> "Gujarat Coast"` — that
would mislabel any non-Indian basin and is therefore NOT reused here).
Rather than hardcode polygons and present a guess as a validation, an
unknown land status is reported as UNKNOWN_NO_LANDMASK. A caller must not
read that as "confirmed at sea".
"""
from __future__ import annotations

import math
from typing import Any

from varuna_contracts.operator_case import (
    LandClassification,
    StartingPoint,
    StartingPointSource,
    StartingPointStatus,
)
from varuna_contracts.schemas import BBox, GeoPoint


def _finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def _in_geographic_bounds(p: GeoPoint) -> bool:
    return -180.0 <= p.lon <= 180.0 and -90.0 <= p.lat <= 90.0


def _point_within_bbox(p: GeoPoint, bbox: BBox) -> bool:
    return (bbox.min_lon <= p.lon <= bbox.max_lon
            and bbox.min_lat <= p.lat <= bbox.max_lat)


def classify_land(point: GeoPoint) -> LandClassification:
    """No authoritative offline land mask exists in this repository — see the
    module docstring. Returning UNKNOWN is the honest answer; callers must
    not treat it as a confirmation that the point is at sea."""
    return LandClassification.UNKNOWN_NO_LANDMASK


def resolve_starting_point(
    detection_value: Any = None,
    origin_value: Any = None,
    *,
    detection_evidence_mode: str | None = None,
    origin_evidence_mode: str | None = None,
) -> StartingPoint:
    """Resolve the case's starting point from already-produced evidence.

    Precedence follows the Starting Point Contract:
      1. validated detection geometry / slick centroid
      2. an explicitly provided origin (Phi) bbox centre
    Anything else -> UNAVAILABLE. Never a default coordinate.

    Accepts either pydantic objects or the plain dicts the OperatorCase
    projection already works with, so this can run on both sides of
    serialisation without a second conversion layer.
    """

    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _as_lonlat(raw: Any) -> tuple[float, float] | None:
        """Return raw floats, NOT a GeoPoint: `GeoPoint` itself enforces
        lon<=180/lat<=90, so building one from an out-of-range upstream value
        raises a ValidationError and would 500 the entire operator view. The
        contract must fail CLOSED with STARTING_POINT_INVALID instead, so the
        range check has to happen before construction."""
        if raw is None:
            return None
        lon, lat = _get(raw, "lon"), _get(raw, "lat")
        if lon is None or lat is None or not _finite(lon, lat):
            return None
        return float(lon), float(lat)

    def _as_bbox(raw: Any) -> BBox | None:
        if raw is None:
            return None
        vals = [_get(raw, k) for k in ("min_lon", "min_lat", "max_lon", "max_lat")]
        if any(v is None for v in vals) or not _finite(*vals):
            return None
        try:
            return BBox(min_lon=vals[0], min_lat=vals[1], max_lon=vals[2], max_lat=vals[3])
        except Exception:
            return None

    # ---- 1. validated detection centroid -------------------------------
    raw_centroid = _as_lonlat(_get(detection_value, "centroid"))
    if raw_centroid is not None:
        c_lon, c_lat = raw_centroid
        if not (-180.0 <= c_lon <= 180.0 and -90.0 <= c_lat <= 90.0):
            return StartingPoint(
                status=StartingPointStatus.INVALID,
                source=StartingPointSource.DETECTION_CENTROID,
                reason=(f"detection centroid ({c_lon}, {c_lat}) is outside "
                        "valid geographic bounds (lon -180..180, lat -90..90)"),
                evidence_mode=detection_evidence_mode,
            )
        centroid = GeoPoint(lon=c_lon, lat=c_lat)
        det_bbox = _as_bbox(_get(detection_value, "bbox"))
        if det_bbox is not None and not _point_within_bbox(centroid, det_bbox):
            return StartingPoint(
                status=StartingPointStatus.INVALID,
                source=StartingPointSource.DETECTION_CENTROID,
                point=centroid,
                reason=("detection centroid lies outside its own detection bbox — "
                        "malformed geometry, refusing to use it as a starting point"),
                evidence_mode=detection_evidence_mode,
            )
        land = classify_land(centroid)
        if land is LandClassification.LAND:
            return StartingPoint(
                status=StartingPointStatus.REJECTED_LAND,
                source=StartingPointSource.DETECTION_CENTROID,
                point=centroid, land_classification=land,
                reason=("detection centroid classifies as land; a maritime spill source "
                        "cannot be promoted from a land position without explicit evidence"),
                evidence_mode=detection_evidence_mode,
            )
        return StartingPoint(
            status=StartingPointStatus.AVAILABLE,
            source=StartingPointSource.DETECTION_CENTROID,
            point=centroid, land_classification=land,
            evidence_mode=detection_evidence_mode,
        )

    # ---- 2. Phi bbox centre --------------------------------------------
    phi_bbox = _as_bbox(_get(origin_value, "bbox"))
    if phi_bbox is not None:
        centre = GeoPoint(lon=(phi_bbox.min_lon + phi_bbox.max_lon) / 2.0,
                          lat=(phi_bbox.min_lat + phi_bbox.max_lat) / 2.0)
        if not _in_geographic_bounds(centre):
            return StartingPoint(
                status=StartingPointStatus.INVALID,
                source=StartingPointSource.PHI_BBOX_CENTER,
                reason="Phi bbox centre is outside valid geographic bounds",
                evidence_mode=origin_evidence_mode,
            )
        land = classify_land(centre)
        if land is LandClassification.LAND:
            return StartingPoint(
                status=StartingPointStatus.REJECTED_LAND,
                source=StartingPointSource.PHI_BBOX_CENTER,
                point=centre, land_classification=land,
                reason="Phi bbox centre classifies as land",
                evidence_mode=origin_evidence_mode,
            )
        return StartingPoint(
            status=StartingPointStatus.AVAILABLE,
            source=StartingPointSource.PHI_BBOX_CENTER,
            point=centre, land_classification=land,
            evidence_mode=origin_evidence_mode,
        )

    return StartingPoint(
        status=StartingPointStatus.UNAVAILABLE,
        reason=("no validated detection centroid and no Phi bbox are available for "
                "this case — no starting point can be derived without fabricating one"),
    )
