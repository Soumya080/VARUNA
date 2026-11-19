"""Tests for the smart-fix channel-binding correction (2026-08-30).

Guards:
  1. The physical evidence behind the fix (band 1 brighter than band 0 in
     100% of a real, deterministic sample of Zenodo training scenes) --
     if this ever stops holding (e.g. Zenodo's source data changes), the
     fix's justification should be re-examined, not silently assumed.
  2. resolve_frozen_v0_2_channel_binding() does exactly one thing: swap.
  3. Nothing about production MC20 Gold or Zenodo Gold changes by the
     mere existence of this function -- it is not called by any existing
     build script.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages"))

from varuna_data_eng.preprocessing.sentinel1_grd_calibration import (  # noqa: E402
    resolve_frozen_v0_2_channel_binding,
)

ZENODO_PART1 = REPO / "data" / "raw" / "zenodo" / "extracted" / "part1"
ZENODO_LOOKALIKE = REPO / "data" / "raw" / "zenodo" / "extracted" / "part2" / "Lookalike"
ZENODO_NO_OIL = REPO / "data" / "raw" / "zenodo" / "extracted" / "part2" / "No_Oil" / "No_oil"

needs_zenodo = pytest.mark.skipif(not ZENODO_PART1.exists(), reason="raw Zenodo corpus not present")


def test_resolve_frozen_v0_2_channel_binding_swaps_deterministically():
    vv = np.full((4, 4), -20.0, dtype=np.float32)
    vh = np.full((4, 4), -30.0, dtype=np.float32)
    ch0, ch1 = resolve_frozen_v0_2_channel_binding(vv, vh)
    assert np.array_equal(ch0, vh) and np.array_equal(ch1, vv)
    # order matters: swapping the call arguments swaps the result
    ch0b, ch1b = resolve_frozen_v0_2_channel_binding(vh, vv)
    assert np.array_equal(ch0b, vv) and np.array_equal(ch1b, vh)


@needs_zenodo
@pytest.mark.parametrize("root,n", [(ZENODO_PART1, 40), (ZENODO_LOOKALIKE, 40), (ZENODO_NO_OIL, 40)])
def test_zenodo_band1_is_systematically_brighter_than_band0(root, n):
    """This is the physical evidence the fix rests on. Deterministic
    (sorted filenames, fixed count) so it reproduces exactly.

    If this test ever fails, the smart-fix's justification (Zenodo's
    band order being the reverse of what array_provider.py assumes)
    should be re-examined before trusting resolve_frozen_v0_2_channel_binding().
    """
    files = sorted(glob.glob(str(root / "*.tif")))[:n]
    assert len(files) == n, f"expected {n} files under {root}, found {len(files)}"
    brighter = []
    for f in files:
        with rasterio.open(f) as src:
            arr = src.read().astype(np.float32)
        b0 = arr[0][np.isfinite(arr[0])]
        b1 = arr[1][np.isfinite(arr[1])]
        brighter.append(b1.mean() > b0.mean())
    frac = sum(brighter) / len(brighter)
    assert frac == 1.0, (
        f"expected band1 > band0 in 100% of {n} scenes under {root} "
        f"(the evidence resolve_frozen_v0_2_channel_binding cites); got {frac:.2%}"
    )


def test_binding_function_does_not_touch_production_gold():
    """resolve_frozen_v0_2_channel_binding is not imported by any Gold
    builder -- its existence must not change build_mc20_event_gold.py's
    or 04_build_gold.py's output."""
    for script in ("scripts/build_mc20_event_gold.py", "scripts/netra_v02/04_build_gold.py"):
        text = (REPO / script).read_text(encoding="utf-8")
        assert "resolve_frozen_v0_2_channel_binding" not in text, (
            f"{script} must not call the smart-fix binding function -- "
            "it is an opt-in diagnostic/inference correction, not a production default"
        )
