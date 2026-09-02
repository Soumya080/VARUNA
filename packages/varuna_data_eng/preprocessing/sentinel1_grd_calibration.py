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


@dataclass(frozen=True)
class NoiseRangeLUT:
    """Sparse (line, pixel) -> thermal-noise-power grid, same shape convention
    as CalibrationLUT. Parsed from a real noise-*.xml; never fabricated."""
    lines: np.ndarray
    pixels: np.ndarray
    noise_power: np.ndarray


@dataclass(frozen=True)
class NoiseAzimuthVector:
    """One <noiseAzimuthVector> entry: a per-swath azimuth-direction noise
    scale factor, constant across a swath's range-sample span and varying
    only with azimuth line."""
    swath: str
    first_range_sample: int
    last_range_sample: int
    line: np.ndarray
    noise_azimuth_lut: np.ndarray


@dataclass(frozen=True)
class NoiseLUT:
    range_lut: NoiseRangeLUT
    azimuth_vectors: tuple[NoiseAzimuthVector, ...]


def parse_noise_lut(noise_xml_path: Path) -> NoiseLUT:
    """Parse a Sentinel-1 GRD noise XML
    (annotation/calibration/noise-s1?-iw-grd-{vv,vh}-*.xml) for its real
    noiseRangeVectorList and noiseAzimuthVectorList. Same real-XML-only
    discipline as parse_calibration_lut -- raises on malformed input,
    never returns a fabricated/default LUT.

    EXPERIMENTAL (Experiment 0, 2026-08-30): this parser and everything
    that consumes it (calibrate_to_db's remove_thermal_noise= path below)
    is additive and opt-in. Nothing that already calls calibrate_to_db()
    without the new keyword arguments is affected -- default behavior is
    byte-for-byte unchanged from before this experiment.
    """
    tree = ET.parse(noise_xml_path)
    root = tree.getroot()

    range_vectors = root.findall(".//noiseRangeVector")
    if not range_vectors:
        raise ValueError(f"No <noiseRangeVector> entries found in {noise_xml_path}")

    lines, pixels_list, noise_list = [], [], []
    for vec in range_vectors:
        line_el = vec.find("line")
        pixel_el = vec.find("pixel")
        noise_el = vec.find("noiseRangeLut")
        if line_el is None or pixel_el is None or noise_el is None:
            raise ValueError(f"Malformed noiseRangeVector in {noise_xml_path}")
        lines.append(int(line_el.text))
        pixels_list.append(np.array([int(p) for p in pixel_el.text.split()]))
        noise_list.append(np.array([float(s) for s in noise_el.text.split()]))

    range_lut = NoiseRangeLUT(
        lines=np.array(lines),
        pixels=np.stack(pixels_list),
        noise_power=np.stack(noise_list),
    )

    az_vectors = []
    for az in root.findall(".//noiseAzimuthVector"):
        def _req_text(tag: str) -> str:
            el = az.find(tag)
            if el is None or el.text is None:
                raise ValueError(f"Malformed noiseAzimuthVector, missing/empty <{tag}> in {noise_xml_path}")
            return el.text

        swath_txt = _req_text("swath")
        frs_txt = _req_text("firstRangeSample")
        lrs_txt = _req_text("lastRangeSample")
        line_txt = _req_text("line")
        lut_txt = _req_text("noiseAzimuthLut")
        az_vectors.append(NoiseAzimuthVector(
            swath=swath_txt,
            first_range_sample=int(frs_txt),
            last_range_sample=int(lrs_txt),
            line=np.array([int(v) for v in line_txt.split()]),
            noise_azimuth_lut=np.array([float(v) for v in lut_txt.split()]),
        ))
    if not az_vectors:
        raise ValueError(f"No <noiseAzimuthVector> entries found in {noise_xml_path}")

    return NoiseLUT(range_lut=range_lut, azimuth_vectors=tuple(az_vectors))


def _interpolate_noise_to_grid(
    noise: NoiseLUT, height: int, width: int, row_offset: int = 0, col_offset: int = 0,
) -> np.ndarray:
    """Interpolate the combined range x azimuth noise-power LUT onto a
    (height, width) crop window, exactly as calibrate_window() in
    scripts/build_mc20_event_gold.py shifts the calibration LUT: the
    LUT's own (line, pixel) coordinates are shifted by (row_offset,
    col_offset) into the crop's local frame before interpolation, rather
    than interpolating in full-scene coordinates and cropping afterward
    (equivalent result, this ordering matches the existing calibration
    code path this experiment must stay consistent with).

    Per the Sentinel-1 product-format spec, total thermal noise power at
    (line, pixel) = noiseRangeLut(line, pixel) * noiseAzimuthLut(line),
    with the azimuth factor selected by whichever swath's range-sample
    span contains that pixel (constant across that span, varies only
    with line).
    """
    from scipy.interpolate import RegularGridInterpolator

    rl = noise.range_lut
    shifted_lines = rl.lines - row_offset
    shifted_pixels = rl.pixels - col_offset
    pixel_axis = shifted_pixels[0]
    range_interp = RegularGridInterpolator(
        (shifted_lines, pixel_axis), rl.noise_power,
        bounds_error=False, fill_value=None,
    )
    line_grid, pixel_grid = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
    points = np.stack([line_grid.ravel(), pixel_grid.ravel()], axis=-1)
    range_grid = range_interp(points).reshape(height, width)

    # Azimuth factor: per-column selection of the swath whose full-scene
    # range-sample span contains this crop column, then 1D interpolation
    # of that swath's line/noiseAzimuthLut at each full-scene row.
    az_grid = np.ones((height, width), dtype=np.float64)
    full_cols = np.arange(width) + col_offset
    full_rows = np.arange(height) + row_offset
    assigned = np.zeros(width, dtype=bool)
    for vec in noise.azimuth_vectors:
        in_span = (full_cols >= vec.first_range_sample) & (full_cols <= vec.last_range_sample)
        if not in_span.any():
            continue
        az_factor_per_row = np.asarray(np.interp(full_rows, vec.line, vec.noise_azimuth_lut))
        az_grid[:, in_span] = az_factor_per_row.reshape(-1, 1)
        assigned |= in_span
    if not assigned.all():
        raise ValueError(
            "Noise azimuth LUT does not cover the full crop width -- "
            f"{int((~assigned).sum())} of {width} columns unassigned. "
            "Refusing to silently fall back to the neutral factor of 1.0 "
            "for an uncovered region."
        )

    return range_grid * az_grid


def calibrate_to_db_denoised(
    dn_array: np.ndarray,
    calibration_xml_path: Path,
    noise_xml_path: Path,
    polarization: Polarization,
    measurement_tiff_path: Path,
    row_offset: int = 0,
    col_offset: int = 0,
    below_noise_policy: str = "floor",
) -> tuple[CalibrationResult, int]:
    """Experiment 0 (2026-08-30): DN -> thermal-noise-subtracted sigma-nought
    -> dB. Additive, opt-in alternative to calibrate_to_db() -- that
    function is completely unmodified and remains the default path used
    by every existing caller (scripts/build_mc20_event_gold.py included).
    This function is called ONLY from diagnostic experiment scripts.

    Real ESA GRD noise-correction formula (Sentinel-1 product spec /
    Copernicus SentiWiki S1 processing, Eq. 5-6: noise is subtracted from
    the power-detected GRD data BEFORE the sigmaNought calibration factor
    is applied):
        NoisePower(line,pixel) = noiseRangeLut(line,pixel) * noiseAzimuthLut(line)
        sigma0_linear = (DN^2 - NoisePower) / sigmaNought^2

    `below_noise_policy` (Experiment A, 2026-08-30) controls what happens
    at pixels where the real, product-supplied noise power exceeds DN^2 --
    i.e. where the scene's backscatter is at or below the sensor's own
    thermal-noise floor and sigma0 is therefore NOT MEASURABLE there:

      "floor" (DEFAULT, unchanged Experiment-0 behavior, kept so that
          experiment stays exactly reproducible): clamp the residual power
          to +1e-6 before log10. This substitutes an ARBITRARY constant
          (~-115 dB after calibration) for an unmeasurable quantity. It
          avoids -inf, but any statistic computed over those pixels then
          reflects the choice of epsilon rather than the scene.

      "mask": set those pixels to NaN instead. Physically the honest
          representation -- below the noise floor the true sigma0 is
          unmeasurable, not "very small" -- and consistent with how
          calibrate_to_db() already marks DN==0 border pixels as NaN, and
          with how apply_netra_normalization() already forces non-finite
          input to the 0.0 nodata sentinel. Prefer this for any
          statistical comparison.

    Returns (CalibrationResult, n_below_noise) where n_below_noise counts
    pixels whose signal power did not exceed the noise floor, under either
    policy.
    """
    if below_noise_policy not in ("floor", "mask"):
        raise ValueError(
            f"below_noise_policy must be 'floor' or 'mask', got {below_noise_policy!r}"
        )
    lut = parse_calibration_lut(calibration_xml_path)
    noise = parse_noise_lut(noise_xml_path)
    from dataclasses import replace as _replace
    shifted_lut = _replace(lut, lines=lut.lines - row_offset, pixels=lut.pixels - col_offset)
    sigma_nought_grid = _interpolate_lut_to_grid(shifted_lut, dn_array.shape[0], dn_array.shape[1])
    noise_power_grid = _interpolate_noise_to_grid(
        noise, dn_array.shape[0], dn_array.shape[1], row_offset, col_offset
    )

    floor_eps = 1e-6  # arbitrary constant; only used by the "floor" policy
    with np.errstate(divide="ignore", invalid="ignore"):
        denoised_power = dn_array.astype(np.float64) ** 2 - noise_power_grid
        below_noise = denoised_power <= floor_eps
        if below_noise_policy == "floor":
            usable_power = np.maximum(denoised_power, floor_eps)
        else:  # "mask" -- unmeasurable, not "very small"
            usable_power = np.where(below_noise, np.nan, denoised_power)
        sigma0_linear = usable_power / (sigma_nought_grid ** 2)
        db = 10.0 * np.log10(sigma0_linear)

    db = np.where(dn_array == 0, np.nan, db)
    n_floored = int(below_noise.sum())

    return CalibrationResult(
        db=db.astype(np.float32),
        polarization=polarization,
        thermal_noise_removed=True,
        source_measurement_path=str(measurement_tiff_path),
        source_calibration_path=str(calibration_xml_path),
    ), n_floored


def resolve_frozen_v0_2_channel_binding(
    physical_vv_db: np.ndarray, physical_vh_db: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Smart-fix investigation (2026-08-30): map REAL, correctly-labeled
    VV/VH arrays (e.g. from a fresh Sentinel-1 .SAFE product, where the two
    polarizations come from two separately-named, unambiguous measurement
    files) onto the two channel SLOTS the frozen NETRA-GOLD-v0.2 model was
    actually trained against -- which are NOT what their normalization-
    record labels say.

    THE EVIDENCE (all measured this task, reproducible from files already
    on disk, none fabricated):

    1. `array_provider.py::RealZenodoArrayProvider` assumes GeoTIFF band 1
       = VV, band 2 = VH, "based on the Zenodo pilot" -- an unverified
       assumption (the raw GeoTIFFs carry zero band descriptions/tags).

    2. Checked directly against 120 real Zenodo scenes across all three
       training sources (40 zenodo_part1, 40 Lookalike, 40 No_Oil): band 1
       is brighter than band 0 in dB in **100% of scenes**, by +12.20 dB
       (part1), +5.00 dB (Lookalike), +11.63 dB (No_Oil) on average.

    3. For natural ocean surfaces, co-polarized (VV) backscatter is ALWAYS
       brighter than cross-polarized (VH) -- cross-pol requires
       depolarization, which weakens the return. A reversal in 100% of 120
       independently-sampled scenes across three separately-collected
       sub-corpora is not scene variation; it is a systematic labeling
       error. Band 0 is physically VH; band 1 is physically VV -- the
       OPPOSITE of what the code assumes.

    4. The frozen checkpoint's `channels.VV` / `channels.VH` normalization
       stats were fit on whatever `RealZenodoArrayProvider` actually fed
       into channel 0 / channel 1 during Gold v0.2's build -- i.e. on
       physical VH (labeled "VV") and physical VV (labeled "VH")
       respectively. The model's learned channel-0/1 semantics are
       internally coherent (verified: it fires normally, max=0.9999, on
       real positive oil tiles built the same mislabeled way) -- they are
       just not what the labels claim.

    5. MC20's own pipeline reads REAL, unambiguous VV and VH from two
       separately-named measurement files (polarization verified against
       each file's own annotation XML in the Experiment-A audit) and, by
       following the code's (wrong) assumption, feeds physical VV into
       the "VV"-labeled normalization slot -- i.e. into channel 0, which
       the model actually learned as physical VH. This function corrects
       that mismatch for inference against THIS frozen checkpoint only.

    THE FIX IS SCOPED NARROWLY: it does not relabel Zenodo, does not
    touch NETRA-GOLD-v0.2, does not retrain, and does not change what
    "VV" and "VH" mean anywhere except at this one inference-time
    boundary, for this one checkpoint's known channel semantics. A
    correctly-labeled NETRA-GOLD-v0.3 should fix `array_provider.py`
    directly instead of ever needing this function again -- this is a
    compatibility shim for a model already trained under the mislabeling,
    not a permanent convention.

    Returns (channel_0_db, channel_1_db) = (physical_vh_db, physical_vv_db).
    """
    return physical_vh_db, physical_vv_db


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
