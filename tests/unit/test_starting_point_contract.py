"""Starting Point Contract — never fabricate an origin.

Covers the resolver directly (varuna_geospatial.starting_point) and the
guarantee that a case with no usable geometry reports UNAVAILABLE rather
than a plausible-looking default coordinate.
"""
import pytest

from varuna_contracts.operator_case import (
    LandClassification,
    StartingPointSource,
    StartingPointStatus,
)
from varuna_geospatial.starting_point import resolve_starting_point


def _detection(centroid=None, bbox=None):
    d = {}
    if centroid is not None:
        d["centroid"] = centroid
    if bbox is not None:
        d["bbox"] = bbox
    return d


VALID_BBOX = {"min_lon": -89.02, "min_lat": 28.90, "max_lon": -88.92, "max_lat": 28.98}
VALID_CENTROID = {"lon": -88.970, "lat": 28.936}


def test_detection_centroid_is_the_primary_source():
    sp = resolve_starting_point(_detection(VALID_CENTROID, VALID_BBOX),
                                detection_evidence_mode="real")
    assert sp.status is StartingPointStatus.AVAILABLE
    assert sp.source is StartingPointSource.DETECTION_CENTROID
    assert sp.point.lon == pytest.approx(-88.970)
    assert sp.point.lat == pytest.approx(28.936)
    assert sp.evidence_mode == "real"


def test_no_evidence_at_all_is_unavailable_not_a_default_coordinate():
    sp = resolve_starting_point(None, None)
    assert sp.status is StartingPointStatus.UNAVAILABLE
    assert sp.point is None
    assert sp.source is StartingPointSource.NONE
    assert "fabricating" in (sp.reason or "")


def test_centroid_outside_geographic_bounds_is_invalid():
    sp = resolve_starting_point(_detection({"lon": 999.0, "lat": 28.9}))
    assert sp.status is StartingPointStatus.INVALID
    assert "geographic bounds" in (sp.reason or "")


def test_centroid_outside_its_own_bbox_is_invalid():
    sp = resolve_starting_point(_detection({"lon": 10.0, "lat": 10.0}, VALID_BBOX))
    assert sp.status is StartingPointStatus.INVALID
    assert "outside its own detection bbox" in (sp.reason or "")


def test_nonfinite_centroid_is_not_used():
    sp = resolve_starting_point(_detection({"lon": float("nan"), "lat": 28.9}))
    assert sp.status is StartingPointStatus.UNAVAILABLE


def test_falls_back_to_phi_bbox_centre_when_no_detection_centroid():
    sp = resolve_starting_point(None, {"bbox": VALID_BBOX}, origin_evidence_mode="real")
    assert sp.status is StartingPointStatus.AVAILABLE
    assert sp.source is StartingPointSource.PHI_BBOX_CENTER
    assert sp.point.lon == pytest.approx(-88.97)
    assert sp.point.lat == pytest.approx(28.94)


def test_land_classification_is_honestly_unknown_not_guessed():
    """No offline land mask ships with this repository; the contract must
    say so rather than claim the point was validated as being at sea."""
    sp = resolve_starting_point(_detection(VALID_CENTROID, VALID_BBOX))
    assert sp.land_classification is LandClassification.UNKNOWN_NO_LANDMASK


def test_accepts_pydantic_objects_as_well_as_dicts():
    from varuna_contracts.schemas import BBox, GeoPoint

    class _Det:
        centroid = GeoPoint(lon=-88.970, lat=28.936)
        bbox = BBox(**VALID_BBOX)

    sp = resolve_starting_point(_Det())
    assert sp.status is StartingPointStatus.AVAILABLE
    assert sp.point.lat == pytest.approx(28.936)


def test_case_valid_replay_exposes_an_available_starting_point():
    """End-to-end through the real projection, not just the resolver."""
    from fastapi.testclient import TestClient

    from apps.api.main import app

    body = TestClient(app).get("/v1/replay/CASE-VALID").json()
    sp = body["starting_point"]
    assert sp["status"] == "STARTING_POINT_AVAILABLE"
    assert sp["source"] == "detection_centroid"
    assert sp["point"]["lon"] == pytest.approx(-88.970)


def test_case_ood_reports_unavailable_and_never_invents_one():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    body = TestClient(app).get("/v1/replay/CASE-OOD").json()
    sp = body["starting_point"]
    assert sp["status"] == "STARTING_POINT_UNAVAILABLE"
    assert sp["point"] is None
