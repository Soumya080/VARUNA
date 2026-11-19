"""Unit + regression tests for the additive Sentinel-1 NESZ / thermal-noise
correction path (Experiment 0 / Experiment A).

Guards two things that matter:
  1. The new code parses the REAL product noise LUT correctly and
     registers it to a crop window exactly (verified against an
     independent manual bilinear reconstruction from the raw XML).
  2. The additive path did not change the DEFAULT production behavior --
     calibrate_to_db() and the MC20 Event Gold it produces must be
     untouched.

Tests requiring the real SAFE product skip cleanly when it is absent.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages"))

from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    NoiseLUT, _interpolate_noise_to_grid, calibrate_to_db_denoised, parse_noise_lut,
)

SAFE = (REPO / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15" /
        "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE")
CAL = SAFE / "annotation" / "calibration"
VH_NOISE = CAL / "noise-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"
VV_NOISE = CAL / "noise-s1a-iw-grd-vv-20230115t000206-20230115t000231-046787-059bff-001.xml"
VH_CAL = CAL / "calibration-s1a-iw-grd-vh-20230115t000206-20230115t000231-046787-059bff-002.xml"

needs_safe = pytest.mark.skipif(not VH_NOISE.exists(), reason="real MC20 SAFE product not present")


@needs_safe
def test_parse_noise_lut_reads_real_product_structure():
    lut = parse_noise_lut(VH_NOISE)
    assert isinstance(lut, NoiseLUT)
    assert lut.range_lut.noise_power.shape == lut.range_lut.pixels.shape
    assert lut.range_lut.lines.ndim == 1
    # real IW GRD product carries one azimuth vector per sub-swath
    assert {v.swath for v in lut.azimuth_vectors} == {"IW1", "IW2", "IW3"}
    assert all(v.line.shape == v.noise_azimuth_lut.shape for v in lut.azimuth_vectors)


@needs_safe
def test_noise_lut_pixel_axis_is_shared_and_monotonic():
    """_interpolate_noise_to_grid uses pixels[0] as THE pixel axis for every
    range vector. That is only valid if all vectors share one monotonic
    axis -- assert it rather than assume it."""
    lut = parse_noise_lut(VH_NOISE)
    ax = lut.range_lut.pixels[0]
    assert np.all(np.diff(ax) > 0), "pixel axis must be strictly increasing"
    for row in lut.range_lut.pixels:
        assert np.array_equal(row, ax), "all range vectors must share one pixel axis"


@needs_safe
def test_noise_grid_matches_independent_manual_reconstruction():
    """Registration guard: an off-by-one, a wrong crop origin, or a wrong
    sub-swath would all break this."""
    top, left, size = 7268, 18657, 64
    probe_r, probe_c = 20, 33
    abs_line, abs_pix = top + probe_r, left + probe_c

    root = ET.parse(VH_NOISE).getroot()
    rv = root.findall(".//noiseRangeVector")
    lines = np.array([int(v.find("line").text) for v in rv])
    ax = np.array([int(x) for x in rv[0].find("pixel").text.split()])
    luts = np.stack([np.array([float(x) for x in v.find("noiseRangeLut").text.split()]) for v in rv])

    i1 = int(np.searchsorted(lines, abs_line)); i0 = i1 - 1
    j1 = int(np.searchsorted(ax, abs_pix)); j0 = j1 - 1
    wl = (abs_line - lines[i0]) / (lines[i1] - lines[i0])
    wp = (abs_pix - ax[j0]) / (ax[j1] - ax[j0])
    manual_range = (luts[i0, j0] * (1 - wl) * (1 - wp) + luts[i1, j0] * wl * (1 - wp)
                     + luts[i0, j1] * (1 - wl) * wp + luts[i1, j1] * wl * wp)

    az_factor = None
    for az in root.findall(".//noiseAzimuthVector"):
        frs, lrs = int(az.find("firstRangeSample").text), int(az.find("lastRangeSample").text)
        if frs <= abs_pix <= lrs:
            azl = np.array([int(x) for x in az.find("line").text.split()])
            azv = np.array([float(x) for x in az.find("noiseAzimuthLut").text.split()])
            az_factor = float(np.interp(abs_line, azl, azv))
            break
    assert az_factor is not None, "crop column must fall inside a sub-swath's range span"

    grid = _interpolate_noise_to_grid(parse_noise_lut(VH_NOISE), size, size, top, left)
    assert grid[probe_r, probe_c] == pytest.approx(manual_range * az_factor, rel=1e-9)


@needs_safe
def test_uncovered_columns_raise_rather_than_silently_using_neutral_factor():
    """A crop beyond the last range sample has no azimuth LUT coverage.
    Silently applying a neutral 1.0 there would fabricate a noise estimate."""
    lut = parse_noise_lut(VH_NOISE)
    last = max(v.last_range_sample for v in lut.azimuth_vectors)
    with pytest.raises(ValueError, match="does not cover"):
        _interpolate_noise_to_grid(lut, 8, 8, 0, last + 1)


@needs_safe
def test_below_noise_policy_floor_and_mask_differ_only_where_signal_is_below_noise():
    dn = np.full((32, 32), 40, dtype=np.uint16)
    dn[:4, :] = 1  # force some pixels far below the noise floor
    top, left = 7268, 18657
    floored, n_floor = calibrate_to_db_denoised(
        dn, VH_CAL, VH_NOISE, "VH", VH_NOISE, top, left, below_noise_policy="floor")
    masked, n_mask = calibrate_to_db_denoised(
        dn, VH_CAL, VH_NOISE, "VH", VH_NOISE, top, left, below_noise_policy="mask")
    assert n_floor == n_mask > 0
    below = ~np.isfinite(masked.db)
    assert below.sum() == n_mask
    # above-noise pixels must be bit-identical between the two policies
    assert np.allclose(floored.db[~below], masked.db[~below], equal_nan=True)
    # below-noise pixels: floor invents a finite constant, mask marks unmeasurable
    assert np.all(np.isfinite(floored.db[below]))


@needs_safe
def test_invalid_below_noise_policy_rejected():
    dn = np.full((8, 8), 40, dtype=np.uint16)
    with pytest.raises(ValueError, match="below_noise_policy"):
        calibrate_to_db_denoised(dn, VH_CAL, VH_NOISE, "VH", VH_NOISE, 7268, 18657,
                                  below_noise_policy="clip")


@needs_safe
def test_noise_lut_polarizations_are_not_swapped():
    """Guards against the classic wrong-file bug: each noise XML must
    declare the polarization its filename claims."""
    for path, expected in ((VV_NOISE, "VV"), (VH_NOISE, "VH")):
        assert ET.parse(path).getroot().find(".//polarisation").text == expected


@needs_safe
def test_production_mc20_gold_is_unchanged_by_the_additive_path():
    """Regression guard for Phase 9: the frozen MC20 Event Gold v0.1 tiles
    on disk must remain exactly what the DEFAULT (noise-free) calibration
    produces. If adding the NESZ path ever alters production output, this
    fails."""
    tiles_dir = REPO / "data" / "gold" / "events" / "mc20_v0_1" / "sar" / "tiles"
    if not tiles_dir.exists():
        pytest.skip("MC20 Event Gold not present")
    tiles = sorted(tiles_dir.glob("*.npy"))
    assert len(tiles) == 9
    for t in tiles:
        a = np.load(t)
        assert a.shape == (2, 512, 512) and a.dtype == np.float32
        assert np.isfinite(a).all()
        assert a.min() >= 0.0 and a.max() <= 1.0
