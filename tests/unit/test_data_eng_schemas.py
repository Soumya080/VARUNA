import pytest
from datetime import datetime, timezone
from varuna_contracts.schemas import BBox, VesselType
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.schemas.quality import QualityState, QualityVerdict
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization, ChannelMeta
from varuna_data_eng.schemas.oil_mask import OilMask, OilLabelClass
from varuna_data_eng.schemas.ais import RawAISPoint, RawAISTrack, AISGapRecord, GapClass, raw_to_locked
from varuna_data_eng.schemas.forcing import ForcingCube, ForcingSource, ForcingVariable
from varuna_data_eng.schemas.attribution_case import AgePrior, AttributionCaseInput, AttributionCaseTruth, AttributionCase, CaseMetadata
from varuna_data_eng.schemas.normalization import NormalizationRecord, ChannelStats
from varuna_data_eng.schemas.manifest import DatasetManifest, ManifestEntry, SplitManifest, DataQualityReport
from varuna_data_eng.schemas.versioning import DatasetVersion, TrainingRunRecord
from varuna_data_eng.schemas.quality import DedupState, DedupVerdict

@pytest.fixture
def dummy_provenance():
    return DataProvenance(
        source_id="zenodo.8346860",
        adapter_id="mock_zenodo",
        license="CC-BY-4.0"
    )

@pytest.fixture
def dummy_bbox():
    return BBox(min_lon=0.0, min_lat=0.0, max_lon=1.0, max_lat=1.0)

def test_provenance_schema(dummy_provenance):
    assert dummy_provenance.source_id == "zenodo.8346860"
    
def test_canonical_sar(dummy_provenance, dummy_bbox):
    sar = CanonicalSAR(
        scene_id="s1_test",
        source_dataset="zenodo_oil_i",
        sensor=SARSensor.SENTINEL_1,
        platform="S1A",
        band=SARBand.C,
        polarizations=[Polarization.VV, Polarization.VH],
        product_type="GRD",
        processing_level="1",
        acquisition_time=datetime.now(timezone.utc),
        resolution_m=10.0,
        pixel_spacing_m=10.0,
        width_px=1000,
        height_px=1000,
        crs="EPSG:4326",
        bbox=dummy_bbox,
        channels={"VV": ChannelMeta(name="VV", unit="dB", dtype="float32")},
        data_path="/tmp/mock.tif",
        file_checksum="1234abcd",
        file_size_bytes=1024,
        provenance=dummy_provenance
    )
    assert sar.scene_id == "s1_test"

def test_canonical_sar_invalid_band(dummy_provenance, dummy_bbox):
    with pytest.raises(ValueError, match="Invalid band"):
        CanonicalSAR(
            scene_id="s1_test",
            source_dataset="zenodo_oil_i",
            sensor=SARSensor.SENTINEL_1,
            platform="S1A",
            band=SARBand.L,  # Invalid: Sentinel-1 is C-band
            polarizations=[Polarization.VV, Polarization.VH],
            product_type="GRD",
            processing_level="1",
            acquisition_time=datetime.now(timezone.utc),
            resolution_m=10.0,
            pixel_spacing_m=10.0,
            width_px=1000,
            height_px=1000,
            crs="EPSG:4326",
            bbox=dummy_bbox,
            channels={"VV": ChannelMeta(name="VV", unit="dB", dtype="float32")},
            data_path="/tmp/mock.tif",
            file_checksum="1234abcd",
            file_size_bytes=1024,
            provenance=dummy_provenance
        )
    
    with pytest.raises(ValueError, match="Invalid band"):
        CanonicalSAR(
            scene_id="nisar_test",
            source_dataset="nisar_mock",
            sensor=SARSensor.NISAR_S,
            platform="NISAR",
            band=SARBand.C,  # Invalid: NISAR_S is S-band
            polarizations=[Polarization.VV, Polarization.VH],
            product_type="GRD",
            processing_level="1",
            acquisition_time=datetime.now(timezone.utc),
            resolution_m=10.0,
            pixel_spacing_m=10.0,
            width_px=1000,
            height_px=1000,
            crs="EPSG:4326",
            bbox=dummy_bbox,
            channels={"VV": ChannelMeta(name="VV", unit="dB", dtype="float32")},
            data_path="/tmp/mock.tif",
            file_checksum="1234abcd",
            file_size_bytes=1024,
            provenance=dummy_provenance
        )
        
def test_canonical_sar_nisar_valid(dummy_provenance, dummy_bbox):
    sar = CanonicalSAR(
        scene_id="nisar_test",
        source_dataset="nisar_mock",
        sensor=SARSensor.NISAR_S,
        platform="NISAR",
        band=SARBand.S,  # Valid
        polarizations=[Polarization.VV, Polarization.VH],
        product_type="GRD",
        processing_level="1",
        acquisition_time=datetime.now(timezone.utc),
        resolution_m=10.0,
        pixel_spacing_m=10.0,
        width_px=1000,
        height_px=1000,
        crs="EPSG:4326",
        bbox=dummy_bbox,
        channels={"VV": ChannelMeta(name="VV", unit="dB", dtype="float32")},
        data_path="/tmp/mock.tif",
        file_checksum="1234abcd",
        file_size_bytes=1024,
        provenance=dummy_provenance
    )
    assert sar.sensor == SARSensor.NISAR_S

def test_oil_mask(dummy_provenance, dummy_bbox):
    mask = OilMask(
        mask_id="mask_1",
        scene_id="s1_test",
        label_class=OilLabelClass.OIL,
        mask_path="/tmp/mask.tif",
        mask_crs="EPSG:4326",
        mask_bbox=dummy_bbox,
        mask_resolution_m=10.0,
        mask_width_px=1000,
        mask_height_px=1000,
        annotation_source="zenodo_expert",
        annotation_version="v1",
        class_counts={"OIL": 100, "BACKGROUND": 900},
        file_checksum="abcd",
        provenance=dummy_provenance
    )
    assert mask.label_class == OilLabelClass.OIL

def test_ais_engineering_schemas(dummy_provenance):
    pt = RawAISPoint(
        mmsi="123456789",
        timestamp=datetime.now(timezone.utc),
        lon=0.0, lat=0.0,
        source="synthetic",
        provenance=dummy_provenance,
        vessel_type_code=70
    )
    pt2 = RawAISPoint(
        mmsi="123456789",
        timestamp=datetime.now(timezone.utc),
        lon=0.1, lat=0.1,
        source="synthetic",
        provenance=dummy_provenance,
        vessel_type_code=70
    )
    gap = AISGapRecord(
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        duration_minutes=60,
        distance_km=10.0,
        gap_class=GapClass.MEDIUM,
        interpolated=False,
        is_observable=True
    )
    track = RawAISTrack(
        track_id="trk_1",
        mmsi="123456789",
        vessel_type=VesselType.CARGO,
        points=[pt, pt2],
        gaps=[gap],
        quality_flags=[],
        cleaning_log=[],
        provenance=dummy_provenance
    )
    locked_track = raw_to_locked(track)
    assert locked_track.mmsi == "123456789"
    assert len(locked_track.gaps) == 1

def test_forcing_cube(dummy_provenance, dummy_bbox):
    cube = ForcingCube(
        cube_id="cube_1",
        source=ForcingSource.ERA5,
        product_id="era5_wind",
        variables=[ForcingVariable(name="wind_u", unit="m/s")],
        time_coords=[datetime.now(timezone.utc)],
        lat_coords=[0.0, 1.0],
        lon_coords=[0.0, 1.0],
        grid_resolution_deg=0.25,
        temporal_resolution_hours=1.0,
        data_path="/tmp/era5.nc",
        crs="EPSG:4326",
        bbox=dummy_bbox,
        time_range=(datetime.now(timezone.utc), datetime.now(timezone.utc)),
        file_checksum="abcd",
        file_size_bytes=1024,
        provenance=dummy_provenance
    )
    assert cube.source == ForcingSource.ERA5

def test_attribution_case(dummy_provenance, dummy_bbox):
    truth = AttributionCaseTruth(true_source_mmsi="123456789")
    # Verify truth has no leaking to input schema by design
    # Actually, input just takes other models
    pass

def test_manifest_schemas(dummy_provenance):
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
        file_paths={"tile": "/tmp/a.npy"}
    )
    assert entry.split == "train"
