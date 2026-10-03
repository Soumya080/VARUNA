"""Tests for the NETRA-GOLD-v0.3 weak-label loader (2026-08-31)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages"))

from varuna_netra.dataset.gold_v03 import (  # noqa: E402
    IGNORE_INDEX,
    GoldV03Error,
    NetraGoldV03Dataset,
)

RECORDS = REPO / "data" / "gold" / "netra_v0_3" / "provenance" / "tile_records_v2.json"
needs_gold = pytest.mark.skipif(not RECORDS.exists(), reason="Gold v0.3 not built")


@needs_gold
@pytest.mark.parametrize("split", ["train", "val", "holdout"])
def test_splits_load_and_are_deterministic(split):
    ds = NetraGoldV03Dataset(RECORDS, split=split, repo_root=REPO)
    assert len(ds) > 0
    ids_a = [r["tile_id"] for r in ds.records]
    ds2 = NetraGoldV03Dataset(RECORDS, split=split, repo_root=REPO)
    ids_b = [r["tile_id"] for r in ds2.records]
    assert ids_a == ids_b == sorted(ids_a), "ordering must be deterministic and sorted"


@needs_gold
def test_excluded_duplicates_are_never_yielded():
    all_recs = json.loads(RECORDS.read_text())
    excluded = {r["tile_id"] for r in all_recs if r["final_split"] == "EXCLUDED_DUPLICATE"}
    assert excluded, "expected some excluded duplicates in this build"
    seen = set()
    for split in ("train", "val", "holdout"):
        seen |= {r["tile_id"] for r in NetraGoldV03Dataset(RECORDS, split=split, repo_root=REPO).records}
    assert not (seen & excluded), "duplicate-excluded tiles must not appear in any split"


@needs_gold
def test_no_scene_appears_in_two_splits():
    scenes = {}
    for split in ("train", "val", "holdout"):
        for r in NetraGoldV03Dataset(RECORDS, split=split, repo_root=REPO).records:
            prev = scenes.get(r["scene_id"])
            assert prev in (None, split), (
                f"scene {r['scene_id']} appears in both {prev} and {split} -- scene-level split violated"
            )
            scenes[r["scene_id"]] = split


@needs_gold
def test_shapes_dtypes_and_no_nan():
    ds = NetraGoldV03Dataset(RECORDS, split="train", repo_root=REPO)
    img, target = ds[0]
    assert img.shape == (2, 512, 512) and img.dtype == torch.float32
    assert target.shape == (512, 512) and target.dtype == torch.int64
    assert torch.isfinite(img).all(), "NaN/Inf must be collapsed before the loader yields"


@needs_gold
def test_ignore_mask_applied_by_default_and_disableable():
    ds_ign = NetraGoldV03Dataset(RECORDS, split="train", repo_root=REPO, apply_ignore=True)
    ds_raw = NetraGoldV03Dataset(RECORDS, split="train", repo_root=REPO, apply_ignore=False)
    # find an oil tile (one that actually has box pixels)
    idx = next(i for i, r in enumerate(ds_ign.records) if r["semantic_class"] == "OIL")
    _, t_ign = ds_ign[idx]
    _, t_raw = ds_raw[idx]
    assert (t_raw == 1).sum() > 0, "expected a positive box region in this tile"
    assert (t_ign == IGNORE_INDEX).sum() == (t_raw == 1).sum(), (
        "every weak-box positive pixel should become IGNORE when apply_ignore=True"
    )
    assert (t_ign == 1).sum() == 0, "no pixel may be asserted as confirmed oil under the ignore policy"


@needs_gold
def test_label_quality_is_weak_box_not_silently_upgraded():
    ds = NetraGoldV03Dataset(RECORDS, split="train", repo_root=REPO, return_meta=True)
    counts = ds.label_quality_counts()
    assert set(counts) == {"WEAK_BOX"}, f"v0.3 labels must stay WEAK_BOX, got {counts}"
    _, _, meta = ds[0]
    assert meta["label_quality"] == "WEAK_BOX"
    assert meta["semantic_class"] in ("OIL", "NEGATIVE_OR_LOOKALIKE")


@needs_gold
def test_normalization_maps_into_unit_range():
    norm = json.loads((REPO / "data" / "gold" / "netra_v0_3" / "reports" /
                       "normalization_report_v2.json").read_text())
    ds = NetraGoldV03Dataset(RECORDS, split="train", repo_root=REPO, normalization=norm)
    img, _ = ds[0]
    assert float(img.min()) >= 0.0 and float(img.max()) <= 1.0


def test_rejects_missing_records_file(tmp_path):
    with pytest.raises(GoldV03Error):
        NetraGoldV03Dataset(tmp_path / "nope.json", split="train", repo_root=REPO)


def test_rejects_bad_split():
    with pytest.raises(ValueError):
        NetraGoldV03Dataset(RECORDS, split="test", repo_root=REPO)


@needs_gold
def test_no_all_ignore_tiles_reach_any_split():
    """An all-ignored target yields NaN under CrossEntropyLoss(ignore_index),
    which would poison every weight via backward. Such tiles must be
    excluded by the manifest, not discovered on the GPU."""
    import numpy as np
    repo_gold = REPO / "data" / "gold" / "netra_v0_3"
    for split in ("train", "val", "holdout"):
        ds = NetraGoldV03Dataset(RECORDS, split=split, repo_root=REPO)
        for r in ds.records:
            ig = np.load(repo_gold / r["split"] / f"{r['tile_id']}_ignore.npy")
            assert ig.mean() <= 0.999, (
                f"{r['tile_id']} in split {split} is ~100% ignored -> NaN loss"
            )
