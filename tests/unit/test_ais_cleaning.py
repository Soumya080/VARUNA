import pytest
from datetime import datetime, timezone, timedelta
from varuna_data_eng.schemas.ais import RawAISPoint, GapClass
from varuna_data_eng.schemas.provenance import DataProvenance
from varuna_data_eng.preprocessing.ais_cleaner import AISCleaner

@pytest.fixture
def dummy_provenance():
    return DataProvenance(source_id="zenodo.123", adapter_id="mock", license="CC-BY")

def test_ais_cleaner_dedup_and_gaps(dummy_provenance):
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    # 1. Start point
    pt1 = RawAISPoint(
        mmsi="123456789", timestamp=base_time, lon=0.0, lat=0.0,
        sog_knots=10.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance
    )
    
    # 2. Duplicate of pt1
    pt2 = RawAISPoint(
        mmsi="123456789", timestamp=base_time, lon=0.0, lat=0.0,
        sog_knots=10.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance
    )
    
    # 3. 2 hours later (LONG gap)
    pt3 = RawAISPoint(
        mmsi="123456789", timestamp=base_time + timedelta(hours=2), lon=0.2, lat=0.2,
        sog_knots=10.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance
    )
    
    # 4. 25 hours later (VERY LONG gap -> splits track)
    pt4 = RawAISPoint(
        mmsi="123456789", timestamp=base_time + timedelta(hours=27), lon=1.0, lat=1.0,
        sog_knots=10.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance
    )
    
    # 5. Normal point following pt4
    pt5 = RawAISPoint(
        mmsi="123456789", timestamp=base_time + timedelta(hours=27, minutes=10), lon=1.01, lat=1.01,
        sog_knots=10.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance
    )
    
    tracks = cleaner.clean([pt1, pt2, pt3, pt4, pt5], "123456789")
    
    # Should result in 2 tracks due to the VERY_LONG gap split
    assert len(tracks) == 2
    
    track1 = tracks[0]
    assert len(track1.points) == 2 # pt1, pt3 (pt2 deduped)
    assert len(track1.gaps) == 1
    assert track1.gaps[0].gap_class == GapClass.MEDIUM
    
    track2 = tracks[1]
    assert len(track2.points) == 2 # pt4, pt5
    assert len(track2.gaps) == 1
    assert track2.gaps[0].gap_class == GapClass.SHORT

def test_ais_cleaner_invalid_coords(dummy_provenance):
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    pt1 = RawAISPoint(
        mmsi="123", timestamp=base_time, lon=200.0, lat=0.0, # Invalid lon
        source="synthetic", provenance=dummy_provenance
    )
    pt2 = RawAISPoint(
        mmsi="123", timestamp=base_time + timedelta(minutes=10), lon=0.0, lat=0.0,
        source="synthetic", provenance=dummy_provenance
    )
    
    tracks = cleaner.clean([pt1, pt2], "123")
    # pt1 rejected, leaving only pt2, which is < 2 points, so no tracks returned
    assert len(tracks) == 0
