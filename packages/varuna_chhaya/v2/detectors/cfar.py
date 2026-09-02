"""Cell-Averaging CFAR (Constant False Alarm Rate) vessel-candidate detector.

Real, classical, well-established SAR ship-detection signal processing — NOT a
placeholder and NOT a neural network. Requires no training, no pretrained
weights, and no auxiliary data (bathymetry, land mask) beyond the calibrated
SAR amplitude itself. This is the algorithm selected in
`reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md` as the detector actually
wired into the live CHHAYA v2 pipeline, precisely because it is simple, has
no missing-input dependency, and its statistic is honestly, structurally
uncalibrated (see `score_type` on the resulting `VesselCandidate`).

Method (standard two-window CA-CFAR, e.g. Novak & Owirka 1994-class formulation
widely used as the candidate-generation stage in SAR ship detection,
including as the first stage of several xView3 competitors):

  For each pixel, estimate local sea-clutter mean/std from an annular
  "training" window (`bg_window_px`) with a smaller "guard" window
  (`guard_window_px`) excluded from the center, so a bright target's own
  pixels never contaminate the clutter estimate used to judge it. The test
  statistic is `(pixel - clutter_mean) / clutter_std` — a standard-deviations-
  above-local-background number, not a probability. Pixels exceeding
  `threshold_sigma` are candidate targets; local peaks are extracted as
  connected components; one `RawDetection` is emitted per connected component
  at its brightest pixel.

`threshold_sigma=6.0` is a literature-typical conservative CFAR multiplier for
SAR ship detection (assuming approximately Gaussian clutter statistics — a
real, standard, but simplifying assumption; true sea clutter is often better
modeled by a K-distribution, which this detector does not attempt). It is
NOT tuned or validated against VARUNA's own Sentinel-1 data in this pass —
callers must treat resulting scores as `RELATIVE_PLAUSIBILITY`, not calibrated
probabilities, exactly per the CHHAYA v2 ranking contract.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from varuna_chhaya.v2.detectors.protocol import RawDetection, VesselDetector

_EPS = 1e-6


def _ring_mean_std(x: np.ndarray, bg_px: int, guard_px: int) -> tuple[np.ndarray, np.ndarray]:
    """Local mean/std of `x` over an annulus: bg_px window minus guard_px window."""
    bg_area = float(bg_px * bg_px)
    guard_area = float(guard_px * guard_px)
    ring_area = max(bg_area - guard_area, 1.0)

    bg_sum = ndimage.uniform_filter(x, size=bg_px, mode="reflect") * bg_area
    guard_sum = ndimage.uniform_filter(x, size=guard_px, mode="reflect") * guard_area
    ring_sum = bg_sum - guard_sum

    x2 = x.astype(np.float64) ** 2
    bg_sum_sq = ndimage.uniform_filter(x2, size=bg_px, mode="reflect") * bg_area
    guard_sum_sq = ndimage.uniform_filter(x2, size=guard_px, mode="reflect") * guard_area
    ring_sum_sq = bg_sum_sq - guard_sum_sq

    ring_mean = ring_sum / ring_area
    ring_mean_sq = ring_sum_sq / ring_area
    ring_var = np.clip(ring_mean_sq - ring_mean ** 2, 0.0, None)
    ring_std = np.sqrt(ring_var)
    return ring_mean, ring_std


class CACFARDetector(VesselDetector):
    detector_id = "cfar_ca_v1"
    detector_mode = "classical"

    def __init__(
        self,
        bg_window_px: int = 41,
        guard_window_px: int = 11,
        threshold_sigma: float = 6.0,
        min_component_px: int = 2,
        max_component_px: int = 4000,
    ):
        if guard_window_px >= bg_window_px:
            raise ValueError("guard_window_px must be smaller than bg_window_px")
        self.bg_window_px = bg_window_px
        self.guard_window_px = guard_window_px
        self.threshold_sigma = threshold_sigma
        self.min_component_px = min_component_px
        self.max_component_px = max_component_px

    def is_available(self) -> bool:
        return True  # no external dependency beyond numpy/scipy, always real

    def get_model_version(self) -> str:
        return (
            f"{self.detector_id}"
            f"(bg={self.bg_window_px},guard={self.guard_window_px},"
            f"sigma={self.threshold_sigma})"
        )

    def detect(self, vh: np.ndarray, vv: np.ndarray | None = None) -> list[RawDetection]:
        if vh.ndim != 2:
            raise ValueError(f"expected a 2D SAR amplitude array, got shape {vh.shape}")
        x = np.nan_to_num(vh.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        x = np.clip(x, 0.0, None)  # amplitude is non-negative by construction

        ring_mean, ring_std = _ring_mean_std(x, self.bg_window_px, self.guard_window_px)
        test_stat = (x - ring_mean) / (ring_std + _EPS)

        mask = test_stat > self.threshold_sigma
        if not mask.any():
            return []

        labels, n = ndimage.label(mask)
        detections: list[RawDetection] = []
        for comp_id in range(1, n + 1):
            comp_mask = labels == comp_id
            n_px = int(comp_mask.sum())
            if n_px < self.min_component_px or n_px > self.max_component_px:
                continue  # too small to trust as a target, or too large (likely land/clutter edge)

            comp_stat = np.where(comp_mask, test_stat, -np.inf)
            peak_flat = int(np.argmax(comp_stat))
            row, col = np.unravel_index(peak_flat, comp_stat.shape)

            rows, cols = np.nonzero(comp_mask)
            length_px = float(max(rows.max() - rows.min(), cols.max() - cols.min()) + 1)

            detections.append(RawDetection(
                row=float(row),
                col=float(col),
                score=float(test_stat[row, col]),
                length_px=length_px,
                n_pixels=n_px,
            ))
        return detections
