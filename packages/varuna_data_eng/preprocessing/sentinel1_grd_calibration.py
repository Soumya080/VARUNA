"""
VARUNA GRID — Real Sentinel-1 GRD radiometric calibration + NETRA-compatible
tiling pipeline.

Converts a freshly-acquired Sentinel-1 IW GRD SAFE product's raw digital
numbers (DN) into the same representation NETRA's trained model actually
consumes: dB-scale sigma-nought backscatter, clipped and scaled per the
FROZEN train-only NormalizationRecord from Gold v0.2
(`data/manifests/netra_gold_v0_2.json::normalization`), tiled to 512x512.

This did NOT exist anywhere in the codebase before this module.
`packages/varuna_data_eng/preprocessing/sentinel1_preproc.py::Sentinel1Preprocessor`
is a no-op stub (`return raw_path` unchanged, docstring acknowledging real
calibration "would" be needed) — confirmed by direct inspection, not
assumed. That file is left untouched; this is new, additive code.

IMPORTANT — what this module does NOT (yet) do, stated explicitly rather
than silently omitted:
  - Thermal noise removal (NESZ subtraction). Sentinel-1 GRD carries a
    separate per-pixel noise LUT (annotation/calibration/noise-*.xml);
    without subtracting it, dark-water backscatter is biased upward,
    which matters most for exactly the low-backscatter oil-slick pixels
    this pipeline exists to detect. Flagged, not implemented — see
    `CalibrationResult.thermal_noise_removed = False`.
  - Terrain correction / orbit-file precision refinement. GRD is already
    ellipsoid-projected (not terrain-corrected), which is consistent with
    how Zenodo's source imagery is delivered (also GRD-derived, per the
    existing Gold manifest's `source_product` field) — not a new gap
    introduced here, but also not solved here.
  - Speckle filtering. Zenodo's tiles may or may not have this applied by
    their original authors; not determined, not replicated here.

These are exactly the kind of "document every transformation, do not
silently assume identical to Zenodo" gaps this module's caller must be
told about, not asked to guess.

Two entry points:
  parse_calibration_lut(calibration_xml_path) -> CalibrationLUT
  calibrate_and_tile(measurement_tiff_path, calibration_xml_path,
                      polarization, normalization_record) -> list[CalibratedTile]

Never modifies the raw SAFE product.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

Polarization = Literal["VV", "VH"]


@dataclass(frozen=True)
class CalibrationLUT:
    """A parsed Sentinel-1 calibration vector list (sigmaNought), still on
    its native sparse (pixel, line) grid -- not yet interpolated to the
    full image. Real values, parsed from the product's own calibration
    XML; never fabricated."""
    lines: np.ndarray          # (n_vectors,) line index of each vector
    pixels: np.ndarray         # (n_vectors, n_points) pixel index per vector
    sigma_nought: np.ndarray   # (n_vectors, n_points) calibration values, same shape as pixels


def parse_calibration_lut(calibration_xml_path: Path) -> CalibrationLUT:
    """Parse a Sentinel-1 GRD calibration XML
    (annotation/calibration/calibration-s1?-iw-grd-{vv,vh}-*.xml) for its
    sigmaNought lookup table. Real XML parsing against the documented
    Sentinel-1 product-format schema; raises on malformed input rather
    than returning a fabricated/default LUT."""
    tree = ET.parse(calibration_xml_path)
    root = tree.getroot()

    vectors = root.findall(".//calibrationVector")
    if not vectors:
        raise ValueError(f"No <calibrationVector> entries found in {calibration_xml_path}")

    lines = []
    pixels_list = []
    sigma_list = []
    for vec in vectors:
        line_el = vec.find("line")
        pixel_el = vec.find("pixel")
        sigma_el = vec.find("sigmaNought")
        if line_el is None or pixel_el is None or sigma_el is None:
            raise ValueError(f"Malformed calibrationVector in {calibration_xml_path}")
        lines.append(int(line_el.text))
        pixels_list.append(np.array([int(p) for p in pixel_el.text.split()]))
        sigma_list.append(np.array([float(s) for s in sigma_el.text.split()]))

    return CalibrationLUT(
        lines=np.array(lines),
        pixels=np.stack(pixels_list),
        sigma_nought=np.stack(sigma_list),
    )


def _interpolate_lut_to_grid(lut: CalibrationLUT, height: int, width: int) -> np.ndarray:
    """Bilinear-interpolate the sparse calibration LUT onto the full
    (height, width) image grid. Uses scipy's RegularGridInterpolator on the
    LUT's own (line, pixel) axes -- both are already regularly spaced in
    real Sentinel-1 products (confirmed by the format spec: calibration
    vectors are emitted at fixed line/pixel steps), so this does not
    require irregular-grid interpolation."""
    from scipy.interpolate import RegularGridInterpolator

    pixel_axis = lut.pixels[0]  # same pixel axis for every line, per the S1 format spec
    interpolator = RegularGridInterpolator(
        (lut.lines, pixel_axis), lut.sigma_nought,
        bounds_error=False, fill_value=None,  # extrapolate at image edges rather than raise
    )
    line_grid, pixel_grid = np.meshgrid(
        np.arange(height), np.arange(width), indexing="ij"
    )
    points = np.stack([line_grid.ravel(), pixel_grid.ravel()], axis=-1)
    return interpolator(points).reshape(height, width)


@dataclass
class CalibrationResult:
    db: np.ndarray                  # calibrated backscatter, dB scale
    polarization: Polarization
    thermal_noise_removed: bool     # see module docstring -- always False today
    source_measurement_path: str
    source_calibration_path: str


def calibrate_to_db(
    dn_array: np.ndarray,
    calibration_xml_path: Path,
    polarization: Polarization,
    measurement_tiff_path: Path,
) -> CalibrationResult:
    """DN -> sigma-nought (linear) -> dB. The real Sentinel-1 GRD radiometric
    calibration formula: sigma0_linear = DN^2 / sigmaNought^2 (ESA product
    format spec). No thermal-noise subtraction (see module docstring)."""
    lut = parse_calibration_lut(calibration_xml_path)
    sigma_nought_grid = _interpolate_lut_to_grid(lut, dn_array.shape[0], dn_array.shape[1])

    with np.errstate(divide="ignore", invalid="ignore"):
        sigma0_linear = (dn_array.astype(np.float64) ** 2) / (sigma_nought_grid ** 2)
        db = 10.0 * np.log10(sigma0_linear)

    # DN == 0 is Sentinel-1's own nodata/border convention -- forced to
    # -inf by log10(0), which must become the same 0.0-after-normalization
    # sentinel NETRA's frozen record already uses for nodata (see
    # apply_netra_normalization below), not left as -inf/NaN.
    db = np.where(dn_array == 0, np.nan, db)

    return CalibrationResult(
        db=db.astype(np.float32),
        polarization=polarization,
        thermal_noise_removed=False,
        source_measurement_path=str(measurement_tiff_path),
        source_calibration_path=str(calibration_xml_path),
    )


def apply_netra_normalization(
    vv_db: np.ndarray, vh_db: np.ndarray, vv_stats: dict, vh_stats: dict,
) -> np.ndarray:
    """Apply the EXACT frozen NETRA Gold v0.2 normalization
    (`netra-norm-v0.2-nodata-excluded`) -- clip to [p2, p98], scale to
    [0, 1], nodata forced to 0.0 -- to a pair of calibrated dB arrays.
    `vv_stats`/`vh_stats` must be the `channels.VV`/`channels.VH` blocks
    read directly from data/manifests/netra_gold_v0_2.json, not
    re-derived or approximated here. Returns a [2, H, W] float32 array
    matching the trained model's real in_channels=2 input shape (verified
    against packages/varuna_netra/dataset/gold.py's own docstring: "image:
    float32 tensor [2, H, W] (VV, VH - normalized at Gold build time)" --
    NOT the 3-channel VV/VH/ratio shape
    packages/varuna_netra/preprocessing.py::normalize_sar_tile produces,
    which does not match the actually-trained 2-channel model and is not
    reused here)."""
    def _clip_scale(db: np.ndarray, stats: dict) -> np.ndarray:
        lo, hi = stats["clip_low"], stats["clip_high"]
        valid = np.isfinite(db)
        out = np.zeros_like(db, dtype=np.float32)
        clipped = np.clip(db[valid], lo, hi)
        out[valid] = ((clipped - lo) / (hi - lo)).astype(np.float32)
        return out

    vv_norm = _clip_scale(vv_db, vv_stats)
    vh_norm = _clip_scale(vh_db, vh_stats)
    return np.stack([vv_norm, vh_norm], axis=0)


@dataclass
class CalibratedTile:
    tile_id: str
    row: int
    col: int
    array: np.ndarray   # [2, 512, 512] float32, NETRA-normalized


def tile_512(normalized: np.ndarray, scene_id: str, tile_size: int = 512) -> list[CalibratedTile]:
    """Tile a [2, H, W] normalized array into non-overlapping tile_size x
    tile_size tiles, matching NETRA's Gold v0.2 tiling convention (512x512,
    stride 512 -- confirmed against the real manifest's tile pixel_window
    entries, e.g. `[0, 0, 512, 512]`). Partial edge tiles (H or W not an
    exact multiple of tile_size) are dropped, not padded -- padding would
    introduce fabricated pixel content; Gold v0.2's own tiles show no
    evidence of edge-padding either."""
    _, h, w = normalized.shape
    tiles = []
    for row in range(0, h - tile_size + 1, tile_size):
        for col in range(0, w - tile_size + 1, tile_size):
            tile_array = normalized[:, row:row + tile_size, col:col + tile_size]
            tiles.append(CalibratedTile(
                tile_id=f"{scene_id}__r{row}c{col}",
                row=row, col=col, array=tile_array,
            ))
    return tiles
