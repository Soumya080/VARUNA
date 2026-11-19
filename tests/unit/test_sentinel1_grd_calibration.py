"""Tests for the Sentinel-1 GRD calibration pipeline.

Uses a small SYNTHETIC calibration XML + DN array fixture (hand-built,
matching the real Sentinel-1 product-format schema for
<calibrationVector> entries) -- NOT real MC20 data, which is not yet
downloaded (blocked on Copernicus Data Space credentials). These tests
prove the calibration math and normalization wiring are correct; they do
not validate against a real scene. That validation is pending acquisition
-- see docs/datasets/MC20_REAL_E2E_ACQUISITION_REPORT.md.
"""
import numpy as np
import pytest

from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (
    apply_netra_normalization,
    calibrate_to_db,
    parse_calibration_lut,
    tile_512,
)

CALIBRATION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<calibration>
  <calibrationVectorList count="3">
    <calibrationVector>
      <line>0</line>
      <pixel>0 5 10</pixel>
      <sigmaNought>2.0 2.0 2.0</sigmaNought>
    </calibrationVector>
    <calibrationVector>
      <line>5</line>
      <pixel>0 5 10</pixel>
      <sigmaNought>2.0 2.0 2.0</sigmaNought>
    </calibrationVector>
    <calibrationVector>
      <line>10</line>
      <pixel>0 5 10</pixel>
      <sigmaNought>2.0 2.0 2.0</sigmaNought>
    </calibrationVector>
  </calibrationVectorList>
</calibration>
"""


@pytest.fixture
def calibration_xml_path(tmp_path):
    p = tmp_path / "calibration-s1a-iw-grd-vv-test.xml"
    p.write_text(CALIBRATION_XML)
    return p


def test_parse_calibration_lut_reads_real_schema_shape(calibration_xml_path):
    lut = parse_calibration_lut(calibration_xml_path)
    assert lut.lines.tolist() == [0, 5, 10]
    assert lut.pixels.shape == (3, 3)
    assert lut.sigma_nought.shape == (3, 3)
    assert np.all(lut.sigma_nought == 2.0)


def test_parse_calibration_lut_raises_on_malformed_xml(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<calibration><calibrationVectorList/></calibration>")
    with pytest.raises(ValueError, match="No <calibrationVector>"):
        parse_calibration_lut(p)


def test_calibrate_to_db_known_dn_produces_correct_sigma0(calibration_xml_path, tmp_path):
    # DN = sigmaNought (== 2.0 everywhere) -> sigma0_linear = DN^2/sigmaNought^2 = 1.0 -> 0 dB
    dn = np.full((11, 11), 2.0, dtype=np.float32)
    measurement_path = tmp_path / "measurement.tiff"
    measurement_path.write_bytes(b"")  # path recorded only, not read by calibrate_to_db
    result = calibrate_to_db(dn, calibration_xml_path, "VV", measurement_path)
    assert result.polarization == "VV"
    assert result.thermal_noise_removed is False
    # allow for interpolation edge effects; check the well-covered interior
    assert np.allclose(result.db[2:9, 2:9], 0.0, atol=1e-3)


def test_calibrate_to_db_zero_dn_becomes_nan_not_negative_infinity(calibration_xml_path, tmp_path):
    dn = np.zeros((11, 11), dtype=np.float32)
    result = calibrate_to_db(dn, calibration_xml_path, "VV", tmp_path / "m.tiff")
    assert np.all(np.isnan(result.db))  # never -inf, never silently 0.0 at this stage


def test_apply_netra_normalization_uses_real_frozen_bounds():
    """Uses the ACTUAL frozen p2/p98 bounds from
    data/manifests/netra_gold_v0_2.json, not invented test values."""
    vv_stats = {"clip_low": -42.475, "clip_high": -13.825000000000003}
    vh_stats = {"clip_low": -33.425, "clip_high": -7.5249999999999915}

    vv_db = np.full((4, 4), -32.0, dtype=np.float32)  # inside range
    vh_db = np.full((4, 4), -20.0, dtype=np.float32)
    out = apply_netra_normalization(vv_db, vh_db, vv_stats, vh_stats)

    assert out.shape == (2, 4, 4)  # 2-channel, matching the real trained model, not 3
    expected_vv = (-32.0 - vv_stats["clip_low"]) / (vv_stats["clip_high"] - vv_stats["clip_low"])
    assert np.allclose(out[0], expected_vv, atol=1e-5)


def test_apply_netra_normalization_clips_out_of_range_values():
    vv_stats = {"clip_low": -42.475, "clip_high": -13.825}
    vh_stats = {"clip_low": -33.425, "clip_high": -7.525}
    vv_db = np.array([[-999.0, 999.0]], dtype=np.float32)
    vh_db = np.array([[-20.0, -20.0]], dtype=np.float32)
    out = apply_netra_normalization(vv_db, vh_db, vv_stats, vh_stats)
    assert out[0, 0, 0] == pytest.approx(0.0)  # clipped to clip_low -> 0.0
    assert out[0, 0, 1] == pytest.approx(1.0)  # clipped to clip_high -> 1.0


def test_apply_netra_normalization_nodata_forced_to_zero():
    vv_stats = {"clip_low": -42.475, "clip_high": -13.825}
    vh_stats = {"clip_low": -33.425, "clip_high": -7.525}
    vv_db = np.array([[np.nan, -32.0]], dtype=np.float32)
    vh_db = np.array([[-20.0, -20.0]], dtype=np.float32)
    out = apply_netra_normalization(vv_db, vh_db, vv_stats, vh_stats)
    assert out[0, 0, 0] == 0.0  # nodata -> 0.0, matching NETRA's frozen convention


def test_tile_512_matches_real_gold_v02_tiling_convention():
    normalized = np.random.rand(2, 1024, 1024).astype(np.float32)
    tiles = tile_512(normalized, scene_id="test_scene")
    assert len(tiles) == 4  # 2x2 non-overlapping 512x512 tiles
    ids = {t.tile_id for t in tiles}
    assert ids == {"test_scene__r0c0", "test_scene__r0c512", "test_scene__r512c0", "test_scene__r512c512"}
    for t in tiles:
        assert t.array.shape == (2, 512, 512)


def test_tile_512_drops_partial_edge_tiles_not_pads():
    normalized = np.random.rand(2, 600, 600).astype(np.float32)
    tiles = tile_512(normalized, scene_id="test_scene")
    assert len(tiles) == 1  # only the one full 512x512 tile; the remaining 88px strip is dropped
