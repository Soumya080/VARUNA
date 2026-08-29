"""Tests for the MC20 Event Gold corpus (data/gold/events/mc20_v0_1/)
and its readiness gate (scripts/check_mc20_event_gold_readiness.py).

Skips cleanly when the event corpus isn't present in this environment
-- this is an integration-style check of a real, built artifact, not a
fully isolated unit test (matching the pattern already established by
test_mc20_readiness.py and test_mc20_sar_calibration_real.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

EVENT_DIR = REPO_ROOT / "data" / "gold" / "events" / "mc20_v0_1"
MANIFEST_PATH = EVENT_DIR / "manifest.json"

pytestmark = pytest.mark.skipif(
    not MANIFEST_PATH.exists(),
    reason="MC20 Event Gold not built in this environment",
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


# ---------------------------------------------------------------------------
# Manifest completeness (Section 11's required fields)
# ---------------------------------------------------------------------------
def test_manifest_has_required_top_level_fields(manifest):
    for key in ("event_id", "case_name", "dataset_version", "creation_timestamp",
                "processing_git_commit", "modalities", "spatial_alignment",
                "temporal_alignment", "netra_training_isolation",
                "locked_evaluation_isolation"):
        assert key in manifest, f"manifest missing required field: {key}"


def test_manifest_has_all_four_modalities(manifest):
    for m in ("sar", "ais", "era5", "cmems"):
        assert m in manifest["modalities"]
        mod = manifest["modalities"][m]
        for key in ("source", "timestamp", "timestamp_status", "crs", "variables", "evidence_mode"):
            assert key in mod, f"{m} modality missing {key}"
        assert mod["evidence_mode"] == "real", f"{m} modality is not evidence_mode=real"


def test_dataset_version_is_mc20_v0_1(manifest):
    assert manifest["dataset_version"] == "mc20_v0_1"


# ---------------------------------------------------------------------------
# SAR tile integrity (Section 16)
# ---------------------------------------------------------------------------
def test_sar_tiles_real_shape_dtype_and_no_nan_inf():
    tiles_dir = EVENT_DIR / "sar" / "tiles"
    tiles = list(tiles_dir.glob("*.npy"))
    assert len(tiles) > 0, "no SAR tiles found"
    for t in tiles:
        arr = np.load(t)
        assert arr.shape == (2, 512, 512), f"{t.name}: wrong shape {arr.shape}"
        assert arr.dtype == np.float32, f"{t.name}: wrong dtype {arr.dtype}"
        assert not np.isnan(arr).any(), f"{t.name}: contains NaN"
        assert not np.isinf(arr).any(), f"{t.name}: contains Inf"
        assert 0.0 <= arr.min() and arr.max() <= 1.0, f"{t.name}: range outside [0,1]"


def test_sar_tile_records_match_tile_files():
    tiles_dir = EVENT_DIR / "sar" / "tiles"
    records = json.loads((EVENT_DIR / "sar" / "tile_records.json").read_text())
    tile_files = {p.stem for p in tiles_dir.glob("*.npy")}
    record_ids = {r["tile_id"] for r in records}
    assert tile_files == record_ids, "tile files and tile_records.json disagree on membership"


def test_sar_tile_records_have_valid_bbox():
    records = json.loads((EVENT_DIR / "sar" / "tile_records.json").read_text())
    for r in records:
        bbox = r["bbox"]
        assert bbox["min_lon"] < bbox["max_lon"]
        assert bbox["min_lat"] < bbox["max_lat"]


def test_sar_normalization_uses_frozen_gold_v0_2_bounds(manifest):
    gold = json.loads((REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json").read_text())
    assert manifest["modalities"]["sar"]["normalization_version"] == gold["normalization"]["normalization_version"]


# ---------------------------------------------------------------------------
# AIS integrity
# ---------------------------------------------------------------------------
def test_ais_join_schema_and_classification():
    d = json.loads((EVENT_DIR / "ais" / "event_ais_join.json").read_text())
    assert d["n_tracks_total"] > 0
    assert d["n_tracks_spatially_matched"] <= d["n_tracks_total"]
    assert d["n_tracks_temporally_matched"] <= d["n_tracks_spatially_matched"]
    for tr in d["tracks"]:
        assert tr["status"] in ("TEMPORALLY_MATCHED", "SPATIALLY_MATCHED", "TEMPORALLY_UNAVAILABLE")
        if tr["status"] == "TEMPORALLY_MATCHED":
            assert tr["temporally_matched"] is True
            assert tr["spatially_matched"] is True
        # never a temporal match without a spatial match first (Section 6's rule)
        if tr["temporally_matched"]:
            assert tr["spatially_matched"]


def test_ais_closest_temporally_matched_reproduces_prior_report_finding():
    """The prior data-track report established MMSI 368181750, 3.26km,
    +16m57s as the nearest scientifically-relevant AIS relationship.
    This must still be reproducible from a fresh, independent
    computation over the same raw data -- not just re-asserted."""
    d = json.loads((EVENT_DIR / "ais" / "event_ais_join.json").read_text())
    closest = d["closest_temporally_matched"]
    assert closest is not None
    assert closest["mmsi"] == "368181750"
    assert abs(closest["distance_km"] - 3.2554) < 0.01
    assert abs(closest["time_delta_seconds"] - 1017.1) < 1.0


# ---------------------------------------------------------------------------
# Forcing integrity
# ---------------------------------------------------------------------------
def test_forcing_cubes_are_sufficient_time_series():
    for name in ("era5_cube.json", "cmems_cube.json"):
        cube = json.loads((EVENT_DIR / "forcing" / name).read_text())
        assert cube["time_series_status"] == "sufficient"
        assert len(cube["time_coords"]) >= 2
        assert len(cube["variables"]) == 2


def test_forcing_cubes_contain_sar_anchor_and_time(manifest):
    ta = manifest["temporal_alignment"]
    sa = manifest["spatial_alignment"]
    assert ta["era5_contains_t_sar"] is True
    assert ta["cmems_contains_t_sar"] is True
    assert sa["sar_era5_contains_anchor"] is True
    assert sa["sar_cmems_contains_anchor"] is True


# ---------------------------------------------------------------------------
# NETRA training isolation (Section 13) -- structural, not just a claim
# ---------------------------------------------------------------------------
def test_netra_gold_dataset_rejects_this_manifest(manifest):
    """The real production loader must refuse to load the event manifest
    as a training split -- proven by actually calling it, not by
    inspecting code and assuming."""
    from varuna_netra.dataset.gold import NetraGoldDataset

    split = manifest["netra_training_isolation"]["split_value"]
    assert split not in ("train", "val", "test"), (
        f"split value {split!r} is a real NETRA training split -- unsafe"
    )
    with pytest.raises(ValueError, match="split must be one of"):
        NetraGoldDataset(manifest_path=MANIFEST_PATH, split=split)


def test_naive_glob_would_find_tiles_but_that_is_not_the_vulnerability():
    """A bare glob under the event corpus DOES find these files -- that
    is expected and fine (scoped to this small event directory, not a
    full data/gold/ recursive walk, which is large and would contend
    with NETRA's active disk I/O for no additional safety information).
    The actual safety property is that NETRA's real loader (gold.py)
    contains no glob/listdir/walk call at all, proven separately by
    source inspection in the next test."""
    tiles_dir = EVENT_DIR / "sar" / "tiles"
    found = list(tiles_dir.glob("*.npy"))
    assert len(found) > 0, "expected a naive glob to trivially find the tile files"


def test_netra_gold_loader_source_contains_no_filesystem_traversal():
    src = (REPO_ROOT / "packages" / "varuna_netra" / "dataset" / "gold.py").read_text()
    for forbidden in ("glob(", "glob.glob", "os.walk", "os.listdir", "rglob(", "iterdir()"):
        assert forbidden not in src, f"gold.py contains {forbidden!r} -- membership would no longer be manifest-only"


# ---------------------------------------------------------------------------
# Locked-evaluation isolation (Section 14)
# ---------------------------------------------------------------------------
def test_no_locked_evaluation_dataset_referenced(manifest):
    from varuna_data_eng.locked_evaluation_guard import locked_dataset_ids

    assert manifest["locked_evaluation_isolation"]["zenodo_part3_used"] is False
    assert manifest["locked_evaluation_isolation"]["essd_used"] is False
    used_ids = {v.get("source") for v in manifest["modalities"].values()}
    assert not (used_ids & set(locked_dataset_ids()))


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------
def test_builder_refuses_to_overwrite_existing_event_gold():
    """The builder must refuse to run again over an existing, non-empty
    v0_1 -- proven by importing and calling its guard logic directly
    rather than re-running the full (expensive) build."""
    import build_mc20_event_gold as builder

    assert builder.OUT_ROOT.exists() and any(builder.OUT_ROOT.iterdir())
    with pytest.raises(SystemExit, match="already exists and is non-empty"):
        builder.main()


# ---------------------------------------------------------------------------
# Readiness gate
# ---------------------------------------------------------------------------
def test_readiness_gate_reports_event_gold_ready():
    import check_mc20_event_gold_readiness as gate

    checks = {
        "SAR_READY": gate.check_sar_ready(),
        "AIS_READY": gate.check_ais_ready(),
        "ERA5_READY": gate.check_era5_ready(),
        "CMEMS_READY": gate.check_cmems_ready(),
    }
    for name, (ok, detail) in checks.items():
        assert ok, f"{name} failed: {detail}"
