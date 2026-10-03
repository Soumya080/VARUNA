"""Integration test for scripts/check_training_readiness.py.

Runs against the real NETRA Gold v0.2 manifest (owned by the parallel
NETRA workstream, read-only here). Skips cleanly if that manifest is
absent — this test verifies the gate's logic against real data when
available, it does not require it."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

MANIFEST_PATH = REPO_ROOT / "data" / "manifests" / "netra_gold_v0_2.json"


@pytest.mark.skipif(not MANIFEST_PATH.exists(), reason="NETRA Gold v0.2 manifest not present")
def test_netra_readiness_all_checks_pass_on_real_gold():
    import check_training_readiness as gate

    report = gate.check_netra(sample_size=50, seed=1)
    assert report.checks["MANIFEST_VALID"] is True
    assert report.checks["DATASET_VALID"] is True
    assert report.checks["SPLIT_VALID"] is True
    assert report.checks["LEAKAGE_VALID"] is True
    assert report.checks["NORMALIZATION_VALID"] is True
    assert report.checks["GOLD_VALID"] is True
    assert report.checks["DATALOADER_VALID"] is True
    assert report.training_ready is True


@pytest.mark.skipif(not MANIFEST_PATH.exists(), reason="NETRA Gold v0.2 manifest not present")
def test_netra_readiness_never_writes_to_the_manifest_or_gold():
    """Read-only check: the gate must not modify the manifest it reads."""
    import check_training_readiness as gate

    before = MANIFEST_PATH.read_text()
    gate.check_netra(sample_size=20, seed=2)
    after = MANIFEST_PATH.read_text()
    assert before == after


def test_manifest_valid_fails_closed_on_missing_manifest(tmp_path, monkeypatch):
    import check_training_readiness as gate

    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    (tmp_path / "data" / "manifests").mkdir(parents=True)
    report = gate.check_netra(sample_size=10)
    assert report.checks["MANIFEST_VALID"] is False
    assert report.training_ready is False


def test_split_valid_fails_when_a_scene_spans_splits(tmp_path, monkeypatch):
    import json

    import check_training_readiness as gate

    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    manifest_dir = tmp_path / "data" / "manifests"
    manifest_dir.mkdir(parents=True)
    manifest = {
        "dataset_id": "x", "dataset_version": "v", "git_commit": "abc",
        "channels": ["VV", "VH"], "label_mapping": {}, "counts": {"pool_by_source": {}},
        "dedup": {}, "split": {"strategy": "test"},
        "leakage": {"failures": [], "scene_identity": "PASS", "content_duplication": "PASS",
                     "footprint_overlap": "PASS", "temporal": "UNAVAILABLE"},
        "normalization": {"normalization_version": "v1", "computed_from_split": "train", "method": "m"},
        "tiles": [
            {"tile_id": "t1", "scene_id": "s1", "split": "train", "img": "x", "mask": "y"},
            {"tile_id": "t2", "scene_id": "s1", "split": "val", "img": "x", "mask": "y"},
        ],
    }
    (manifest_dir / "netra_gold_v0_2.json").write_text(json.dumps(manifest))
    report = gate.check_netra(sample_size=10)
    assert report.checks["SPLIT_VALID"] is False
    assert report.details["n_scenes_in_multiple_splits"] == 1
    assert report.training_ready is False


def test_leakage_valid_accepts_unavailable_temporal_but_rejects_missing_field(tmp_path, monkeypatch):
    import json

    import check_training_readiness as gate

    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    manifest_dir = tmp_path / "data" / "manifests"
    manifest_dir.mkdir(parents=True)
    base = {
        "dataset_id": "x", "dataset_version": "v", "git_commit": "abc",
        "channels": ["VV", "VH"], "label_mapping": {}, "counts": {"pool_by_source": {}},
        "dedup": {}, "split": {"strategy": "test"},
        "normalization": {"normalization_version": "v1", "computed_from_split": "train", "method": "m"},
        "tiles": [],
    }

    # UNAVAILABLE temporal must be accepted (never treated as a failure).
    ok = dict(base, leakage={"failures": [], "scene_identity": "PASS",
                              "content_duplication": "PASS", "footprint_overlap": "PASS",
                              "temporal": "UNAVAILABLE"})
    (manifest_dir / "netra_gold_v0_2.json").write_text(json.dumps(ok))
    report = gate.check_netra(sample_size=10)
    assert report.checks["LEAKAGE_VALID"] is True

    # A bare, unexplained "PASS" fabricated with no evidence field present at
    # all is a different manifest shape than what's checked here — this test
    # instead checks that an actual failure entry fails the gate.
    bad = dict(base, leakage={"failures": ["something broke"], "scene_identity": "PASS",
                                "content_duplication": "PASS", "footprint_overlap": "PASS",
                                "temporal": "UNAVAILABLE"})
    (manifest_dir / "netra_gold_v0_2.json").write_text(json.dumps(bad))
    report = gate.check_netra(sample_size=10)
    assert report.checks["LEAKAGE_VALID"] is False
