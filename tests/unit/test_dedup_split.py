import pytest
from datetime import datetime, timezone, timedelta
from varuna_contracts.schemas import BBox
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.pipeline.dedup_pipeline import DedupPipeline
from varuna_data_eng.schemas.quality import QualityState, QualityVerdict, DedupState, DedupVerdict
from varuna_data_eng.schemas.manifest import ManifestEntry
from varuna_data_eng.pipeline.split_engine import SplitEngine
from varuna_data_eng.pipeline.leakage_guard import LeakageGuard

@pytest.fixture
def dummy_provenance():
    return DataProvenance(source_id="mock", adapter_id="mock", license="CC-BY")

@pytest.fixture
def base_sar(dummy_provenance):
    return CanonicalSAR(
        scene_id="s1_test",
        source_dataset="test",
        sensor=SARSensor.SENTINEL_1,
        platform="S1A",
        band=SARBand.C,
        polarizations=[Polarization.VV],
        product_type="GRD",
        processing_level="1",
        acquisition_time=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        resolution_m=10.0,
        pixel_spacing_m=10.0,
        width_px=1000,
        height_px=1000,
        crs="EPSG:4326",
        bbox=BBox.model_construct(min_lon=0.0, max_lon=1.0, min_lat=0.0, max_lat=1.0),
        channels={},
        data_path="/mock",
        file_checksum="123",
        file_size_bytes=100,
        provenance=dummy_provenance
    )

def test_dedup_pipeline_duplicates(base_sar):
    pipeline = DedupPipeline()
    sar2 = base_sar.model_copy()
    sar2.scene_id = "s1_dup"
    # Same time and bbox => duplicate
    
    results = pipeline.process([base_sar, sar2])
    assert len(results) == 2
    
    kept = [r for r in results if r[1].verdict == DedupVerdict.KEEP]
    dups = [r for r in results if r[1].verdict == DedupVerdict.DUPLICATE]
    
    assert len(kept) == 1
    assert len(dups) == 1
    assert dups[0][1].duplicate_of == kept[0][0].scene_id

def test_dedup_pipeline_different_time(base_sar):
    pipeline = DedupPipeline()
    sar2 = base_sar.model_copy()
    sar2.scene_id = "s1_new"
    sar2.acquisition_time = base_sar.acquisition_time + timedelta(hours=1)
    
    results = pipeline.process([base_sar, sar2])
    kept = [r for r in results if r[1].verdict == DedupVerdict.KEEP]
    assert len(kept) == 2

def test_split_and_leakage_guard():
    entries = []
    for i in range(100):
        entries.append(ManifestEntry(
            sample_id=f"samp_{i}",
            scene_id=f"scene_{i}",
            content_hash="abc",
            split="unassigned",
            sensor="SENTINEL_1",
            region="mediterranean",
            acquisition_date=datetime.now(timezone.utc),
            quality_state=QualityState(overall_verdict=QualityVerdict.PASS),
            dedup_state=DedupState(verdict=DedupVerdict.KEEP),
            file_paths={}
        ))
        
    engine = SplitEngine(seed=42)
    splits = engine.split(entries, train_ratio=0.7, val_ratio=0.15)
    
    # Verify deterministic counts (roughly 70, 15, 15 due to hashing 100 items)
    assert len(splits["train"]) > 0
    assert len(splits["val"]) > 0
    assert len(splits["test"]) > 0
    
    guard = LeakageGuard()
    assert guard.check_leakage(splits) == True
    
    # Introduce deliberate leakage
    splits["train"].append(splits["test"][0])
    assert guard.check_leakage(splits) == False
