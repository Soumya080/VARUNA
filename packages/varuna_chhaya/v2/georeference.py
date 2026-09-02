"""Phase 3 — georeferencing.

Converts detector pixel outputs into geographic coordinates and validates
them. VARUNA's SAR ingestion does not currently attach real ground-control-
point geocoding per scene (checked: no such artifact under
`packages/varuna_data_eng/preprocessing/`) — so this module uses a documented,
explicit approximation: a linear affine mapping from pixel space onto the
scene's own `BBox` (the same bbox already carried on every scene through the
existing pipeline). This is a standard, honest simplification (equivalent to
"ground-range, north-up, no terrain correction") — NOT full GCP-based
geocoding. It is accurate enough to place a candidate within its scene and
reject impossible coordinates, and is explicitly logged as an approximation
on every candidate's `EvidenceEnvelope.quality.extra["georef_method"]`
rather than silently presented as survey-grade geocoding.

Validated, not hardcoded:
  - resulting lon/lat within [-180,180]/[-90,90] (schema-enforced by GeoPoint)
  - resulting point within (a small margin around) the scene's own bbox
  - pixel row/col within the array's actual shape
  - acquisition timestamp present and not absurdly displaced from case time
Any failure sets `geolocation_valid=False` with a specific reason — the
candidate is kept (never silently dropped) so the caller can report
`INVALID_GEOLOCATION` rather than just fewer detections.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from varuna_contracts.schemas import BBox, GeoPoint

MAX_ACQUISITION_SKEW = timedelta(hours=6)  # candidate time vs. case/scene reference time
BBOX_MARGIN_DEG = 0.02  # ~2km at the equator; tolerates the affine approximation's edge error


@dataclass(frozen=True)
class SceneGeoTransform:
    """Linear pixel->geo mapping for one scene. See module docstring for the
    documented limitation (no GCP correction)."""
    bbox: BBox
    n_rows: int
    n_cols: int

    def pixel_to_lonlat(self, row: float, col: float) -> tuple[float, float]:
        lon = self.bbox.min_lon + (col / max(self.n_cols - 1, 1)) * (self.bbox.max_lon - self.bbox.min_lon)
        # image row 0 is the northernmost row (standard raster convention)
        lat = self.bbox.max_lat - (row / max(self.n_rows - 1, 1)) * (self.bbox.max_lat - self.bbox.min_lat)
        return lon, lat


@dataclass
class GeoreferenceResult:
    position: GeoPoint | None
    valid: bool
    rejection_reason: str | None


def georeference_candidate(
    row: float,
    col: float,
    transform: SceneGeoTransform,
    acquisition_time: datetime,
    case_reference_time: datetime | None = None,
) -> GeoreferenceResult:
    if not (0 <= row < transform.n_rows) or not (0 <= col < transform.n_cols):
        return GeoreferenceResult(None, False, f"pixel ({row},{col}) outside scene array {transform.n_rows}x{transform.n_cols}")

    lon, lat = transform.pixel_to_lonlat(row, col)

    if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
        return GeoreferenceResult(None, False, f"computed coordinate ({lon},{lat}) out of valid CRS range")

    b = transform.bbox
    if not (b.min_lon - BBOX_MARGIN_DEG <= lon <= b.max_lon + BBOX_MARGIN_DEG
            and b.min_lat - BBOX_MARGIN_DEG <= lat <= b.max_lat + BBOX_MARGIN_DEG):
        return GeoreferenceResult(None, False, f"coordinate ({lon},{lat}) falls outside scene bbox {b} beyond tolerance")

    if case_reference_time is not None:
        skew = abs(acquisition_time - case_reference_time)
        if skew > MAX_ACQUISITION_SKEW:
            return GeoreferenceResult(
                GeoPoint(lon=lon, lat=lat), False,
                f"acquisition_time skew {skew} exceeds {MAX_ACQUISITION_SKEW} from case reference time",
            )

    return GeoreferenceResult(GeoPoint(lon=lon, lat=lat), True, None)
