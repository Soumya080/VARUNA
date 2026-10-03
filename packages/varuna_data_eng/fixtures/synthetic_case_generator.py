from datetime import datetime, timezone, timedelta
from typing import List
from varuna_contracts.schemas import GeoPoint, BBox, VesselType
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR, SARSensor, SARBand, Polarization
from varuna_data_eng.schemas.oil_mask import OilMask, OilLabelClass
from varuna_data_eng.schemas.ais import RawAISPoint, RawAISTrack, raw_to_locked
from varuna_data_eng.schemas.forcing import (
    ForcingCube, ForcingSource, SpatialCoverageStatus, TimeSeriesStatus,
)
from varuna_data_eng.schemas.attribution_case import (
    AttributionCase, AttributionCaseInput, AttributionCaseTruth, CaseMetadata, AgePrior
)
from varuna_data_eng.schemas.provenance import DataProvenance

class SyntheticCaseGenerator:
    """Generates synthetic AttributionCase scenarios for M10 integration."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def generate_case(self, case_id: str = "CASE-SYNTH-001") -> AttributionCase:
        prov = DataProvenance(source_id="synthetic", adapter_id="mock", license="CC-0")
        
        obs_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        bbox = BBox.model_construct(min_lon=0.0, max_lon=1.0, min_lat=0.0, max_lat=1.0)
        
        sar = CanonicalSAR(
            scene_id="synth_s1",
            source_dataset="synth",
            sensor=SARSensor.SENTINEL_1,
            platform="S1A",
            band=SARBand.C,
            polarizations=[Polarization.VV],
            product_type="GRD",
            processing_level="1",
            acquisition_time=obs_time,
            resolution_m=10.0,
            pixel_spacing_m=10.0,
            width_px=1000,
            height_px=1000,
            crs="EPSG:4326",
            bbox=bbox,
            channels={},
            data_path="/synth/sar.tif",
            file_checksum="123",
            file_size_bytes=100,
            provenance=prov
        )
        
        mask = OilMask(
            mask_id="mask_1",
            scene_id="synth_s1",
            label_class=OilLabelClass.OIL,
            mask_path="/synth/mask.tif",
            mask_crs="EPSG:4326",
            mask_bbox=bbox,
            mask_resolution_m=10.0,
            mask_width_px=1000,
            mask_height_px=1000,
            annotation_source="synthetic_expert",
            annotation_version="v1",
            class_counts={"OIL": 1000},
            file_checksum="123",
            provenance=prov
        )
        
        forcing = ForcingCube(
            cube_id="f_1",
            source=ForcingSource.ERA5,
            product_id="era5",
            variables=[],
            time_coords=[obs_time - timedelta(hours=24), obs_time],
            lat_coords=[0.0, 1.0],
            lon_coords=[0.0, 1.0],
            grid_resolution_deg=0.25,
            temporal_resolution_hours=1.0,
            data_path="/synth/era5.nc",
            crs="EPSG:4326",
            bbox=bbox,
            time_range=(obs_time - timedelta(hours=24), obs_time),
            file_checksum="123",
            file_size_bytes=100,
            provenance=prov,
            # 2 real time steps -> honestly sufficient; single reconciled
            # bbox -> full coverage. This is a synthetic fixture, not a
            # real ERA5/CMEMS read, but the flags must still reflect what
            # was actually constructed rather than a silent default.
            time_series_status=TimeSeriesStatus.SUFFICIENT,
            spatial_coverage_status=SpatialCoverageStatus.FULL,
        )
        
        pt1 = RawAISPoint(
            mmsi="123456789", timestamp=obs_time - timedelta(hours=2), lon=0.5, lat=0.5, source="synthetic", provenance=prov
        )
        pt2 = RawAISPoint(
            mmsi="123456789", timestamp=obs_time - timedelta(hours=1), lon=0.6, lat=0.6, source="synthetic", provenance=prov
        )

        raw_track = RawAISTrack(
            track_id="trk_1",
            mmsi="123456789",
            vessel_name="SYNTH_VESSEL",
            vessel_type=VesselType.TANKER,
            points=[pt1, pt2],
            gaps=[],
            quality_flags=[],
            cleaning_log=[],
            provenance=prov
        )
        
        locked_track = raw_to_locked(raw_track)

        input_data = AttributionCaseInput(
            slick_observation=sar,
            slick_mask=mask,
            observation_time=obs_time,
            age_prior=AgePrior(mean_hours=6.0, std_hours=1.0, source="synthetic"),
            ais_tracks=[locked_track],
            forcing=forcing,
            candidate_vessels=["123456789"]
        )
        
        truth_data = AttributionCaseTruth(
            true_source_mmsi="123456789",
            true_release_point=GeoPoint.model_construct(lon=0.5, lat=0.5),
            true_release_time=obs_time - timedelta(hours=2),
            true_slick_age_hours=2.0,
            generation_method="synthetic"
        )
        
        metadata = CaseMetadata(
            case_version="v1",
            created_at=datetime.now(timezone.utc),
            provenance=prov
        )
        
        return AttributionCase(
            case_id=case_id,
            input=input_data,
            truth=truth_data,
            metadata=metadata
        )
