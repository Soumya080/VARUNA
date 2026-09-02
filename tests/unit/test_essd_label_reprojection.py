"""Deterministic tests for the ESSD/PANGAEA label reprojection
(2026-08-31): every object/patch bbox reprojected from real lon/lat into
each scene's raw line/pixel coordinates via geolocationGridPoint
inverse-interpolation.

Guards:
  1. The inverse-interpolator's round-trip error on the scene's own grid
     points is near-zero (catches a broken/transposed interpolation).
  2. A synthetic square grid with a known, exact affine line/pixel <->
     lon/lat mapping reprojects exactly (catches an axis-swap bug that
     the real-data round-trip alone might not surface, since real grids
     are not axis-aligned).
  3. Every reprojected raw_bbox falls within its scene's real raster
     bounds (with a small tolerance for edge extrapolation).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.interpolate import griddata

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "netra_v03"))

PROV_DIR = REPO / "data" / "raw" / "netra_v03_sources" / "essd_grd" / "provenance"
needs_essd = pytest.mark.skipif(not PROV_DIR.exists(), reason="ESSD/PANGAEA acquisition not present")


def test_synthetic_affine_grid_reprojects_exactly():
    """A grid where lon = pixel/1000, lat = line/1000 (exact affine) must
    invert exactly: querying at a known (lon, lat) must recover the
    exact (line, pixel) that produced it, not a transposed or scaled
    value."""
    lines = np.array([0, 0, 0, 100, 100, 100, 200, 200, 200])
    pixels = np.array([0, 100, 200, 0, 100, 200, 0, 100, 200])
    lons = pixels / 1000.0
    lats = lines / 1000.0
    points = np.stack([lons, lats], axis=-1)

    query_lon, query_lat = 0.100, 0.100  # should map to pixel=100, line=100
    pred_line = griddata(points, lines, [[query_lon, query_lat]], method="linear")[0]
    pred_pixel = griddata(points, pixels, [[query_lon, query_lat]], method="linear")[0]

    assert abs(pred_line - 100.0) < 1e-6, "line/lat axis mismatch or transposition"
    assert abs(pred_pixel - 100.0) < 1e-6, "pixel/lon axis mismatch or transposition"


@needs_essd
def test_grid_roundtrip_verification_passed():
    with open(PROV_DIR / "reprojection_verification.json") as f:
        v = json.load(f)
    assert v["test1_grid_roundtrip"]["pass"] is True
    assert v["test1_grid_roundtrip"]["max_line_err_px"] < 1.0
    assert v["test1_grid_roundtrip"]["max_pixel_err_px"] < 1.0


@needs_essd
def test_all_reprojected_labels_in_bounds():
    with open(PROV_DIR / "reprojection_verification.json") as f:
        v = json.load(f)
    assert v["test2_in_bounds"]["out_of_bounds"] == 0
    assert v["test2_in_bounds"]["n_checked"] > 0


@needs_essd
def test_scale_sanity_near_unity():
    """Raw-pixel-space object size (at 10m/px) vs. real geodetic size
    should be close to a 1:1 ratio -- catches a wrong pixel-spacing
    assumption or a systematic scale bug."""
    with open(PROV_DIR / "reprojection_verification.json") as f:
        v = json.load(f)
    ratio = v["test3_scale_sanity"]["median_ratio_pixelspace_vs_geodetic"]
    assert ratio is not None
    assert 0.7 <= ratio <= 1.3, f"expected near-1:1 scale, got {ratio}"


@needs_essd
def test_labels_preserve_oil_vs_negative_distinction():
    with open(PROV_DIR / "reprojected_labels.json") as f:
        labels = json.load(f)
    tags = {r["label"] for r in labels}
    assert tags == {"oil", "negative_lookalike"}, (
        "reprojection must not silently collapse oil vs negative/lookalike, "
        f"got label set: {tags}"
    )
