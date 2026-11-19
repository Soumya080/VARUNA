import pytest
from datetime import datetime, timezone
from varuna_contracts.schemas import BBox, VesselType
from varuna_contracts.evidence import TrustState
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization
from varuna_data_eng.schemas.ais import RawAISPoint, RawAISTrack
from varuna_data_eng.pipeline.quality_engine import QualityEngine
from varuna_data_eng.pipeline.data_guard_v2 import DataGuardV2
from varuna_data_eng.schemas.quality import QualityVerdict

@pytest.fixture
def dummy_provenance():
    return DataProvenance(source_id="zenodo.123", adapter_id="mock", license="CC-BY")

@pytest.fixture
def valid_sar(dummy_provenance):
    return CanonicalSAR(
        scene_id="s1_test",
        source_dataset="test",
        sensor=SARSensor.SENTINEL_1,
        platform="S1A",
        band=SARBand.C,
        polarizations=[Polarization.VV],
        product_type="GRD",
        processing_level="1",
        acquisition_time=datetime.now(timezone.utc),
        resolution_m=10.0,
        pixel_spacing_m=10.0,
        width_px=1000,
        height_px=1000,
        crs="EPSG:4326",
        bbox=BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0),
        channels={},
        data_path="/mock",
        file_checksum="123",
        file_size_bytes=100,
        provenance=dummy_provenance
    )

def test_quality_engine_valid_sar(valid_sar):
    engine = QualityEngine(synthetic_mode=True)
    state = engine.validate_sar(valid_sar)
    assert state.overall_verdict == QualityVerdict.PASS

def test_quality_engine_invalid_bbox(valid_sar):
    # Bypass Pydantic validation for test using model_construct
    valid_sar.bbox = BBox.model_construct(min_lon=200.0, max_lon=1.0, min_lat=0.0, max_lat=1.0)
    engine = QualityEngine(synthetic_mode=True)
    state = engine.validate_sar(valid_sar)
    assert state.overall_verdict == QualityVerdict.REJECT

def test_data_guard_v2(valid_sar):
    guard = DataGuardV2(synthetic_mode=True)
    trust = guard.evaluate(valid_sar)
    assert trust == TrustState.TRUSTED

    valid_sar.bbox = BBox.model_construct(min_lon=200.0, max_lon=1.0, min_lat=0.0, max_lat=1.0)
    trust_rejected = guard.evaluate(valid_sar)
    assert trust_rejected == TrustState.QUARANTINED
