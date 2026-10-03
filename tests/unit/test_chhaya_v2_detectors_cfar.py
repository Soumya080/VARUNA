"""SAR detector normalization / CFAR candidate-generation tests, and the
xView3 NOT_CONFIGURED-detector contract test."""
import numpy as np
import pytest

from varuna_chhaya.v2.detectors.cfar import CACFARDetector
from varuna_chhaya.v2.detectors.protocol import VesselDetectorUnavailable
from varuna_chhaya.v2.detectors.xview3_frcnn import XView3FasterRCNNMultihead


def _clutter_scene(shape=(200, 200), seed=7, clutter_mean=0.05, clutter_std=0.01):
    rng = np.random.RandomState(seed)
    return np.clip(rng.normal(clutter_mean, clutter_std, size=shape), 0.0, None)


def test_cfar_is_always_available():
    det = CACFARDetector()
    assert det.is_available() is True


def test_cfar_finds_a_bright_target_against_clutter():
    scene = _clutter_scene()
    # a real vessel return spans multiple pixels; min_component_px=2 (default)
    # correctly rejects a single isolated hot pixel as noise, so the target
    # fixture must too, to test the detector honestly rather than around it.
    scene[99:101, 99:101] = 5.0  # far brighter than clutter -> should trip CFAR
    det = CACFARDetector(bg_window_px=41, guard_window_px=11, threshold_sigma=6.0)
    detections = det.detect(scene)
    assert len(detections) >= 1
    hit = min(detections, key=lambda d: abs(d.row - 100) + abs(d.col - 100))
    assert abs(hit.row - 100) <= 2
    assert abs(hit.col - 100) <= 2
    assert hit.score > 6.0


def test_cfar_finds_no_targets_in_pure_clutter():
    scene = _clutter_scene(seed=99)
    det = CACFARDetector(threshold_sigma=6.0)
    detections = det.detect(scene)
    assert detections == []


def test_cfar_rejects_non_2d_input():
    det = CACFARDetector()
    with pytest.raises(ValueError):
        det.detect(np.zeros((10, 10, 2)))


def test_cfar_score_is_deterministic_across_runs():
    scene = _clutter_scene()
    scene[50, 60] = 4.0
    det = CACFARDetector()
    d1 = det.detect(scene)
    d2 = det.detect(scene)
    assert [(d.row, d.col, d.score) for d in d1] == [(d.row, d.col, d.score) for d in d2]


def test_cfar_get_model_version_reports_real_parameters():
    det = CACFARDetector(threshold_sigma=6.5)
    v = det.get_model_version()
    assert "cfar_ca_v1" in v
    assert "6.5" in v


def test_xview3_detector_reports_unavailable_by_default():
    det = XView3FasterRCNNMultihead()
    assert det.is_available() is False


def test_xview3_detector_raises_not_fabricates():
    det = XView3FasterRCNNMultihead()
    with pytest.raises(VesselDetectorUnavailable, match="bathymetry"):
        det.detect(np.zeros((10, 10)))
