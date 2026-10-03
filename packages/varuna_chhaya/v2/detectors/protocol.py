"""Vessel-detector plugin protocol.

`detector_source` is a swappable component by design: today it's the real,
classical CA-CFAR detector (`cfar.py`). A pretrained neural detector
(`xview3_frcnn.py`) is documented and structurally verified but reports itself
unavailable rather than running with a fabricated input channel — see that
module's docstring and `reports/chhaya_v2/CHHAYA_V2_BENCHMARK_REPORT.md`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RawDetection:
    """One detector-native candidate, in scene pixel space. Nothing here is
    geographic yet — that conversion, and its validation, happens in
    `georeference.py` and is a distinct, auditable step."""
    row: float
    col: float
    score: float                     # detector-native statistic, UNCALIBRATED
    length_px: float | None = None   # None when the detector cannot estimate it
    n_pixels: int | None = None      # connected-component size, for explainability


class VesselDetectorUnavailable(RuntimeError):
    """Raised by `detect()` when a detector cannot honestly produce output —
    e.g. a required input (bathymetry, a second polarization) is missing, or
    model weights are not present. Callers MUST treat this as
    SAR_EVIDENCE_UNAVAILABLE, never as "zero candidates found" — those are
    different claims and must not be conflated."""


class VesselDetector(ABC):
    detector_id: str
    detector_mode: str  # "classical" | "pretrained_neural"

    @abstractmethod
    def is_available(self) -> bool:
        """Whether `detect()` can honestly run right now, in this environment,
        against the inputs this deployment can actually supply. Must not
        return True on the hope that missing inputs won't matter."""

    @abstractmethod
    def detect(self, vh: np.ndarray, vv: np.ndarray | None = None) -> list[RawDetection]:
        """vh/vv are linear-scale (not dB) calibrated SAR amplitude arrays for
        one scene/chip, same shape. Raises VesselDetectorUnavailable rather
        than returning [] when it cannot honestly run."""

    @abstractmethod
    def get_model_version(self) -> str: ...
