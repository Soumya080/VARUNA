"""Tests for the real-SAFE calibration validation
(scripts/validate_mc20_sar_calibration.py), against the actual MC20
Sentinel-1 GRD product when present on disk.

Skips cleanly when the ~1.74GB SAFE product isn't present -- this is
deliberately an integration-style check of a real product, not a fully
isolated unit test (that role belongs to
test_sentinel1_grd_calibration.py's synthetic-fixture tests, which prove
math correctness independent of any specific downloaded product)."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SAFE_DIR = (
    REPO_ROOT / "data" / "raw" / "sentinel1_grd" / "mc20_2023-01-15"
    / "S1A_IW_GRDH_1SDV_20230115T000206_20230115T000231_046787_059BFF_44F2.SAFE"
)
REPORT_PATH = REPO_ROOT / "reports" / "mc20_sar_calibration_validation.json"

pytestmark = pytest.mark.skipif(
    not SAFE_DIR.exists(),
    reason="Real MC20 SAFE product not present in this environment (credential-gated download)",
)


def _load_or_run():
    if REPORT_PATH.exists():
        return json.loads(REPORT_PATH.read_text())
    import subprocess
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_mc20_sar_calibration.py")],
        check=True, cwd=REPO_ROOT,
    )
    return json.loads(REPORT_PATH.read_text())


def test_calibration_report_exists_and_is_real():
    result = _load_or_run()
    assert result["n_tiles_512"] > 0, "must produce at least one real 512x512 tile"


def test_anchor_geolocation_is_close_to_mc20():
    result = _load_or_run()
    g = result["anchor_geolocation_lookup"]
    # Real geolocationGrid points are sparse (~210 for the whole scene);
    # the nearest one need not be exact, just genuinely close.
    assert abs(g["lat"] - 28.936) < 0.5
    assert abs(g["lon"] - (-88.970)) < 0.5


def test_db_values_are_physically_plausible():
    result = _load_or_run()
    vv_lo, vv_hi = result["vv_db_range"]
    vh_lo, vh_hi = result["vh_db_range"]
    # Real Sentinel-1 ocean/oil backscatter in dB is bounded well within
    # [-60, 40] for any genuine calibration -- catches a broken LUT
    # interpolation (e.g. divide-by-zero producing +-inf-scale garbage)
    # without asserting a narrow scene-specific range.
    assert -60 < vv_lo < vv_hi < 40
    assert -60 < vh_lo < vh_hi < 40


def test_normalized_output_has_no_nan_or_inf():
    result = _load_or_run()
    assert result["normalized_has_nan"] is False
    assert result["normalized_has_inf"] is False
    lo, hi = result["normalized_range"]
    assert 0.0 <= lo <= hi <= 1.0


def test_normalization_used_the_frozen_gold_v0_2_bounds():
    result = _load_or_run()
    gold = json.loads((REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json").read_text())
    frozen = gold["normalization"]["channels"]
    assert result["vv_stats_used"]["clip_low"] == frozen["VV"]["clip_low"]
    assert result["vv_stats_used"]["clip_high"] == frozen["VV"]["clip_high"]
    assert result["vh_stats_used"]["clip_low"] == frozen["VH"]["clip_low"]
    assert result["vh_stats_used"]["clip_high"] == frozen["VH"]["clip_high"]
