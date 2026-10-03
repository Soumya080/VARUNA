import pytest
import numpy as np
from datetime import datetime, timezone
from varuna_contracts.schemas import BBox
from varuna_data_eng.pipeline.normalizer import Normalizer
from varuna_data_eng.pipeline.tiler import Tiler
from varuna_data_eng.pipeline.manifest_builder import ManifestBuilder
from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict
from varuna_data_eng.schemas.manifest import ManifestEntry, SplitManifest
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization, ChannelMeta

@pytest.fixture
def dummy_provenance():
    return DataProvenance(source_id="mock", adapter_id="mock", license="CC-BY")

@pytest.fixture
def dummy_sar(dummy_provenance):
    return CanonicalSAR(
        scene_id="s1_tile_test",
        source_dataset="zenodo_oil_i",
        sensor=SARSensor.SENTINEL_1,
        platform="S1A",
        band=SARBand.C,
        polarizations=[Polarization.VV],
        product_type="GRD",
        processing_level="1",
        acquisition_time=datetime.now(timezone.utc),
        resolution_m=10.0,
        pixel_spacing_m=10.0,
        width_px=1024,
        height_px=1024,
        crs="EPSG:4326",
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        channels={"VV": ChannelMeta(name="VV", unit="dB", dtype="float32")},
        data_path="/tmp/mock.tif",
        file_checksum="1234abcd",
        file_size_bytes=1024,
        provenance=dummy_provenance,
    )

def test_normalizer():
    # Provide reproducible normal distributed array for train
    np.random.seed(42)
    train_arrays = {
        "VV": np.random.randn(100, 100).astype(np.float32)
    }
    
    normalizer = Normalizer()
    record = normalizer.compute_stats("v1", "SENTINEL_1", train_arrays)
    
    assert "VV" in record.channels
    stats = record.channels["VV"]
    assert np.isclose(stats.mean, 0.0, atol=0.1)
    
    # Test apply
    test_arr = np.array([[100.0, -100.0]]) # Should clip to p2 and p98
    normalized = normalizer.apply(test_arr, "VV", record)
    
    # After normalization and 0-1 scaling, values should be within 0 and 1
    assert np.max(normalized) <= 1.0
    assert np.min(normalized) >= 0.0

def test_tiler(dummy_sar):
    arr = np.zeros((1024, 1024))
    tiler = Tiler(tile_size=512, stride=512)
    tiles = tiler.tile_array(dummy_sar, arr, split="train", source="unit_test")

    assert len(tiles) == 4
    first = tiles[0]
    assert first.pixel_window.width == 512
    assert first.pixel_window.height == 512
    assert first.parent_scene_id == dummy_sar.scene_id
    assert first.split == "train"
    assert first.source == "unit_test"
    assert first.sensor == "SENTINEL_1"
    assert first.provenance == dummy_sar.provenance
    assert first.bbox is not None

    tiler_overlap = Tiler(tile_size=512, stride=256)
    tiles_overlap = tiler_overlap.tile_array(dummy_sar, arr, split="val", source="unit_test")
    # (1024 - 512)/256 + 1 = 3 in each dimension -> 9 tiles
    assert len(tiles_overlap) == 9
    assert all(t.split == "val" for t in tiles_overlap)
    # rows/columns are distinct grid coordinates, not just pixel offsets
    assert {(t.row, t.column) for t in tiles_overlap} == {(r, c) for r in range(3) for c in range(3)}

def test_manifest_builder(dummy_provenance):
    entry = ManifestEntry(
        sample_id="samp_1",
        scene_id="scene_1",
        content_hash="abc",
        split="train",
        sensor="SENTINEL_1",
        region="mediterranean",
        acquisition_date=datetime.now(timezone.utc),
        quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
        dedup_state=DedupState(verdict=DedupVerdict.KEEP),
        file_paths={}
    )
    
    splits = SplitManifest(
        strategy="spatial",
        group_key="scene_id",
        split_counts={"train": 1},
        seed=42,
        frozen_at=datetime.now(timezone.utc)
    )
    
    builder = ManifestBuilder()
    manifest = builder.build("oil_data", "v1", [entry], splits, dummy_provenance)
    
    assert manifest.dataset_id == "oil_data"
    assert manifest.quality_report.total_samples == 1
    assert manifest.quality_report.passed == 1
    assert manifest.sensor_distribution["SENTINEL_1"] == 1
