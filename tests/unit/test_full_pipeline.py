"""M6.5 repair round 2: integration tests proving FullPipeline actually
executes end-to-end, DataGuard/dedup/split/leakage/tiling/normalization are
wired together in the right order, and quarantined/duplicate scenes never
reach GOLD (manifest samples or tiles).
"""
import pytest
from datetime import datetime, timedelta, timezone

from varuna_contracts.schemas import BBox
from varuna_data_eng.pipeline.full_pipeline import FullPipeline
from varuna_data_eng.pipeline.array_provider import DeterministicSyntheticArrayProvider
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization, ChannelMeta
from varuna_data_eng.schemas.oil_mask import OilMask, OilLabelClass
from varuna_data_eng.schemas.provenance import DataProvenance


def _prov(source_id="zenodo.8346860"):
    return DataProvenance(source_id=source_id, adapter_id="mock_zenodo", license="CC-BY-4.0")


def _bbox(min_lon, min_lat, span=1.0):
    return BBox(min_lon=min_lon, min_lat=min_lat, max_lon=min_lon + span, max_lat=min_lat + span)


def _sar(scene_id, checksum, acquisition_time, bbox, sensor=SARSensor.SENTINEL_1, band=SARBand.C):
    return CanonicalSAR(
        scene_id=scene_id,
        source_dataset="zenodo_oil_i",
        sensor=sensor,
        platform="S1A",
        band=band,
        polarizations=[Polarization.VV, Polarization.VH],
        product_type="GRD",
        processing_level="1",
        acquisition_time=acquisition_time,
        resolution_m=10.0,
        pixel_spacing_m=10.0,
        width_px=1000,
        height_px=1000,
        crs="EPSG:4326",
        bbox=bbox,
        channels={
            "VV": ChannelMeta(name="VV", unit="dB", dtype="float32"),
            "VH": ChannelMeta(name="VH", unit="dB", dtype="float32"),
        },
        data_path=f"/synth/{scene_id}.tif",
        file_checksum=checksum,
        file_size_bytes=1024,
        provenance=_prov(),
    )


def _many_scenes(n, base_time, base_bbox_offset=0.0, region_stride=3.0):
    """Generates n well-separated scenes (in both time and space) so a
    real geographic/temporal split has enough spread to actually produce
    non-degenerate train/val/test groups."""
    scenes = []
    for i in range(n):
        t = base_time + timedelta(days=30 * i)
        bbox = _bbox(base_bbox_offset + region_stride * i, base_bbox_offset + region_stride * i)
        scenes.append(_sar(f"scene_{i:03d}", f"chk_{i:03d}", t, bbox))
    return scenes


@pytest.fixture
def base_time():
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_full_pipeline_end_to_end(base_time):
    """process_raw_dataset() must actually execute and produce a manifest."""
    sar_list = _many_scenes(12, base_time)
    pipeline = FullPipeline(seed=1, synthetic_mode=True, split_strategy="geographic_temporal", tile_size=16)
    manifest = pipeline.process_raw_dataset("oil_test", "v1", sar_list, mask_list=[])

    assert manifest.dataset_id == "oil_test"
    assert manifest.quality_report.total_samples == len(sar_list)
    assert manifest.normalization_stats is not None
    assert sum(manifest.splits.split_counts.values()) == len(sar_list)


def test_dataguard_quarantine_blocks_gold(base_time, monkeypatch):
    """A scene DataGuard quarantines must never reach the manifest or produce tiles."""
    good = _sar("good_1", "chk_good", base_time, _bbox(0.0, 0.0))
    bad = _sar("bad_1", "chk_bad", base_time + timedelta(days=1), _bbox(20.0, 20.0))

    pipeline = FullPipeline(seed=2, synthetic_mode=True, split_strategy="hash_random", tile_size=16)

    # Force the "bad" scene to be quarantined regardless of its actual content.
    real_evaluate = pipeline.guard.evaluate

    def fake_evaluate(artifact):
        if getattr(artifact, "scene_id", None) == "bad_1":
            from varuna_contracts.evidence import TrustState
            return TrustState.QUARANTINED
        return real_evaluate(artifact)

    monkeypatch.setattr(pipeline.guard, "evaluate", fake_evaluate)

    # Need enough scenes for a train split to exist.
    extra = _many_scenes(8, base_time + timedelta(days=100), base_bbox_offset=50.0)
    manifest = pipeline.process_raw_dataset("oil_test", "v1", [good, bad] + extra, mask_list=[])

    sample_ids = {s.scene_id for s in manifest.samples}
    assert "bad_1" not in sample_ids
    assert "good_1" in sample_ids
    assert all(t.parent_scene_id != "bad_1" for t in pipeline.last_run_tiles)


def test_duplicate_excluded_manifest(base_time):
    """A duplicate scene (same sensor/platform, close in time+space) must be
    excluded from the final manifest, but the pipeline must still run."""
    original = _sar("orig_1", "chk_orig", base_time, _bbox(0.0, 0.0))
    duplicate = _sar("dup_1", "chk_dup", base_time + timedelta(seconds=10), _bbox(0.0, 0.0))
    extra = _many_scenes(8, base_time + timedelta(days=100), base_bbox_offset=50.0)

    pipeline = FullPipeline(seed=3, synthetic_mode=True, split_strategy="hash_random", tile_size=16)
    manifest = pipeline.process_raw_dataset("oil_test", "v1", [original, duplicate] + extra, mask_list=[])

    sample_ids = {s.scene_id for s in manifest.samples}
    # Exactly one of the overlapping pair survives dedup.
    assert len(sample_ids.intersection({"orig_1", "dup_1"})) == 1


def test_geographic_split(base_time):
    from varuna_data_eng.pipeline.split_engine import SplitEngine
    from varuna_data_eng.schemas.manifest import ManifestEntry
    from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict

    def entry(scene_id, region, days):
        return ManifestEntry(
            sample_id=f"s_{scene_id}", scene_id=scene_id, content_hash="x",
            split="unassigned", sensor="SENTINEL_1", region=region,
            acquisition_date=base_time + timedelta(days=days),
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP), file_paths={},
        )

    # Same region -> same split, regardless of scene_id/time.
    entries = [entry(f"r1_{i}", "region_A", i) for i in range(5)] + \
              [entry(f"r2_{i}", "region_B", i) for i in range(5)]

    engine = SplitEngine(seed=42, strategy="geographic")
    result = engine.split(entries)

    assigned = {e.scene_id: split for split, es in result.items() for e in es}
    region_a_splits = {assigned[f"r1_{i}"] for i in range(5)}
    region_b_splits = {assigned[f"r2_{i}"] for i in range(5)}
    assert len(region_a_splits) == 1, "same region must land in one split"
    assert len(region_b_splits) == 1


def test_temporal_split(base_time):
    from varuna_data_eng.pipeline.split_engine import SplitEngine
    from varuna_data_eng.schemas.manifest import ManifestEntry
    from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict

    def entry(scene_id, region, days):
        return ManifestEntry(
            sample_id=f"s_{scene_id}", scene_id=scene_id, content_hash="x",
            split="unassigned", sensor="SENTINEL_1", region=region,
            acquisition_date=base_time + timedelta(days=days),
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP), file_paths={},
        )

    # Same calendar month -> same split, regardless of region/scene_id.
    entries = [entry(f"jan_{i}", f"region_{i}", i) for i in range(5)] + \
              [entry(f"jul_{i}", f"region_{i}", 180 + i) for i in range(5)]

    engine = SplitEngine(seed=42, strategy="temporal")
    result = engine.split(entries)

    assigned = {e.scene_id: split for split, es in result.items() for e in es}
    jan_splits = {assigned[f"jan_{i}"] for i in range(5)}
    jul_splits = {assigned[f"jul_{i}"] for i in range(5)}
    assert len(jan_splits) == 1, "same acquisition month must land in one split"
    assert len(jul_splits) == 1


def test_geographic_temporal_split(base_time):
    from varuna_data_eng.pipeline.split_engine import SplitEngine
    from varuna_data_eng.schemas.manifest import ManifestEntry
    from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict

    def entry(scene_id, region, days):
        return ManifestEntry(
            sample_id=f"s_{scene_id}", scene_id=scene_id, content_hash="x",
            split="unassigned", sensor="SENTINEL_1", region=region,
            acquisition_date=base_time + timedelta(days=days),
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP), file_paths={},
        )

    # Same (region, month) group -> same split.
    entries = [entry(f"g_{i}", "region_A", 0) for i in range(5)]
    entries += [entry(f"g_other_{i}", "region_B", 180) for i in range(5)]

    engine = SplitEngine(seed=42, strategy="geographic_temporal")
    result = engine.split(entries)
    assigned = {e.scene_id: split for split, es in result.items() for e in es}

    group_a_splits = {assigned[f"g_{i}"] for i in range(5)}
    group_b_splits = {assigned[f"g_other_{i}"] for i in range(5)}
    assert len(group_a_splits) == 1
    assert len(group_b_splits) == 1

    with pytest.raises(ValueError):
        SplitEngine(strategy="spatial_block")


def test_val_test_leakage(base_time):
    """LeakageGuard must catch leakage between EVERY split pair, not just
    train/test."""
    from varuna_data_eng.pipeline.leakage_guard import LeakageGuard
    from varuna_data_eng.schemas.manifest import ManifestEntry
    from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict

    def entry(scene_id):
        return ManifestEntry(
            sample_id=f"s_{scene_id}", scene_id=scene_id, content_hash="x",
            split="unassigned", sensor="SENTINEL_1", region="r",
            acquisition_date=base_time,
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP), file_paths={},
        )

    close_bbox = _bbox(0.0, 0.0)
    near_bbox = _bbox(0.001, 0.001)  # ~100m away, well within default 50km policy
    far_bbox = _bbox(30.0, 30.0)

    val_scene = _sar("val_leaky", "chk_v", base_time, close_bbox)
    test_scene_close = _sar("test_leaky", "chk_t", base_time, near_bbox)

    guard = LeakageGuard()

    # val vs test leakage (close in space AND time) must be caught even
    # though train vs test and train vs val are clean.
    train_scene = _sar("train_far", "chk_tr", base_time, far_bbox)
    splits = {
        "train": [entry("train_far")],
        "val": [entry("val_leaky")],
        "test": [entry("test_leaky")],
    }
    sar_map = {"train_far": train_scene, "val_leaky": val_scene, "test_leaky": test_scene_close}

    assert guard.check_leakage(splits, sar_map=sar_map) is False


def test_train_val_leakage(base_time):
    from varuna_data_eng.pipeline.leakage_guard import LeakageGuard
    from varuna_data_eng.schemas.manifest import ManifestEntry
    from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict

    def entry(scene_id):
        return ManifestEntry(
            sample_id=f"s_{scene_id}", scene_id=scene_id, content_hash="x",
            split="unassigned", sensor="SENTINEL_1", region="r",
            acquisition_date=base_time,
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP), file_paths={},
        )

    train_scene = _sar("train_leaky", "chk_tr", base_time, _bbox(0.0, 0.0))
    val_scene = _sar("val_leaky", "chk_v", base_time, _bbox(0.001, 0.001))
    test_scene = _sar("test_far", "chk_t", base_time, _bbox(40.0, 40.0))

    guard = LeakageGuard()
    splits = {
        "train": [entry("train_leaky")],
        "val": [entry("val_leaky")],
        "test": [entry("test_far")],
    }
    sar_map = {"train_leaky": train_scene, "val_leaky": val_scene, "test_far": test_scene}

    assert guard.check_leakage(splits, sar_map=sar_map) is False


def test_safe_separation_no_leakage(base_time):
    from varuna_data_eng.pipeline.leakage_guard import LeakageGuard
    from varuna_data_eng.schemas.manifest import ManifestEntry
    from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict

    def entry(scene_id):
        return ManifestEntry(
            sample_id=f"s_{scene_id}", scene_id=scene_id, content_hash="x",
            split="unassigned", sensor="SENTINEL_1", region="r",
            acquisition_date=base_time,
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP), file_paths={},
        )

    train_scene = _sar("train_ok", "chk_tr", base_time, _bbox(0.0, 0.0))
    val_scene = _sar("val_ok", "chk_v", base_time + timedelta(days=365), _bbox(40.0, 40.0))
    test_scene = _sar("test_ok", "chk_t", base_time + timedelta(days=730), _bbox(80.0, 80.0))

    guard = LeakageGuard()
    splits = {
        "train": [entry("train_ok")],
        "val": [entry("val_ok")],
        "test": [entry("test_ok")],
    }
    sar_map = {"train_ok": train_scene, "val_ok": val_scene, "test_ok": test_scene}

    assert guard.check_leakage(splits, sar_map=sar_map) is True


def test_tile_provenance(base_time):
    sar = _sar("prov_scene", "chk_p", base_time, _bbox(0.0, 0.0))
    provider = DeterministicSyntheticArrayProvider(seed=7, shape=(32, 32))
    channels = provider.load_channels(sar)

    from varuna_data_eng.pipeline.tiler import Tiler
    tiler = Tiler(tile_size=16, stride=16)
    tiles = tiler.tile_array(sar, channels["VV"], split="train", source="unit_test_ds")

    assert len(tiles) == 4
    for t in tiles:
        assert t.parent_scene_id == "prov_scene"
        assert t.split == "train"
        assert t.source == "unit_test_ds"
        assert t.sensor == "SENTINEL_1"
        assert t.provenance.source_id == sar.provenance.source_id


def test_split_before_tile(base_time):
    """A quarantined scene must never produce tiles at all — proving tiling
    only ever runs on scenes that already survived the split step."""
    good = _sar("good_split", "chk_g", base_time, _bbox(0.0, 0.0))
    bad = _sar("quarantined_split", "chk_b", base_time + timedelta(days=1), _bbox(10.0, 10.0))
    extra = _many_scenes(8, base_time + timedelta(days=200), base_bbox_offset=60.0)

    pipeline = FullPipeline(seed=5, synthetic_mode=True, split_strategy="hash_random", tile_size=16)

    real_evaluate = pipeline.guard.evaluate

    def fake_evaluate(artifact):
        if getattr(artifact, "scene_id", None) == "quarantined_split":
            from varuna_contracts.evidence import TrustState
            return TrustState.QUARANTINED
        return real_evaluate(artifact)

    import unittest.mock
    with unittest.mock.patch.object(pipeline.guard, "evaluate", side_effect=fake_evaluate):
        manifest = pipeline.process_raw_dataset("oil_test", "v1", [good, bad] + extra, mask_list=[])

    # Every tile must belong to a scene that has a split assignment in the manifest.
    manifest_scene_ids = {s.scene_id for s in manifest.samples}
    for t in pipeline.last_run_tiles:
        assert t.parent_scene_id in manifest_scene_ids
        assert t.split in ("train", "val", "test")
    assert "quarantined_split" not in manifest_scene_ids
    assert all(t.parent_scene_id != "quarantined_split" for t in pipeline.last_run_tiles)


def test_train_only_normalization(base_time):
    sar_list = _many_scenes(12, base_time)
    pipeline = FullPipeline(seed=9, synthetic_mode=True, split_strategy="hash_random", tile_size=16)
    manifest = pipeline.process_raw_dataset("oil_test", "v1", sar_list, mask_list=[])

    assert manifest.normalization_stats is not None
    assert manifest.normalization_stats.computed_from_split == "train"
    assert "VV" in manifest.normalization_stats.channels
    stats = manifest.normalization_stats.channels["VV"]
    # Must reflect real (deterministic synthetic) statistics, not a
    # placeholder all-zero array (which would give mean=std=0).
    assert not (stats.mean == 0.0 and stats.std == 0.0)

    # The same frozen record is what would be applied to val/test — there is
    # exactly one normalization_stats object on the manifest, not one per split.
    assert manifest.normalization_stats.n_samples > 0


def test_full_pipeline_rejects_placeholder_normalization_when_no_train_split():
    """If, after split assignment, there is no train-split entry at all, the
    pipeline must fail loudly rather than compute statistics from nothing."""
    pipeline = FullPipeline(seed=11, synthetic_mode=True, split_strategy="hash_random", tile_size=16)
    with pytest.raises(ValueError):
        pipeline.process_raw_dataset("oil_test", "v1", [], mask_list=[])
