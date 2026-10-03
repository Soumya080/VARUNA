"""Phase 3 tests: coordinate validation / georeferencing."""
from datetime import datetime, timedelta, timezone

import pytest

from varuna_chhaya.v2.georeference import (
    MAX_ACQUISITION_SKEW,
    SceneGeoTransform,
    georeference_candidate,
)
from varuna_contracts.schemas import BBox

BBOX = BBox(min_lon=70.0, min_lat=10.0, max_lon=71.0, max_lat=11.0)
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_center_pixel_maps_inside_bbox():
    tr = SceneGeoTransform(bbox=BBOX, n_rows=100, n_cols=100)
    result = georeference_candidate(50, 50, tr, T0)
    assert result.valid
    assert BBOX.min_lon <= result.position.lon <= BBOX.max_lon
    assert BBOX.min_lat <= result.position.lat <= BBOX.max_lat


def test_row0_is_northernmost():
    tr = SceneGeoTransform(bbox=BBOX, n_rows=100, n_cols=100)
    top = georeference_candidate(0, 50, tr, T0)
    bottom = georeference_candidate(99, 50, tr, T0)
    assert top.position.lat > bottom.position.lat


def test_out_of_bounds_pixel_rejected():
    tr = SceneGeoTransform(bbox=BBOX, n_rows=100, n_cols=100)
    result = georeference_candidate(500, 50, tr, T0)
    assert not result.valid
    assert result.position is None
    assert "outside scene array" in result.rejection_reason


def test_acquisition_time_skew_rejected():
    tr = SceneGeoTransform(bbox=BBOX, n_rows=100, n_cols=100)
    late = T0 + MAX_ACQUISITION_SKEW + timedelta(minutes=1)
    result = georeference_candidate(50, 50, tr, late, case_reference_time=T0)
    assert not result.valid
    assert result.position is not None  # position still computed and returned for audit
    assert "skew" in result.rejection_reason


def test_acquisition_time_within_tolerance_accepted():
    tr = SceneGeoTransform(bbox=BBOX, n_rows=100, n_cols=100)
    close = T0 + timedelta(minutes=5)
    result = georeference_candidate(50, 50, tr, close, case_reference_time=T0)
    assert result.valid


@pytest.mark.parametrize("row,col", [(-1, 50), (50, -1), (100, 50), (50, 100)])
def test_negative_and_edge_out_of_range_rejected(row, col):
    tr = SceneGeoTransform(bbox=BBOX, n_rows=100, n_cols=100)
    result = georeference_candidate(row, col, tr, T0)
    assert not result.valid
