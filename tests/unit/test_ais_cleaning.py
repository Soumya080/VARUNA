from datetime import UTC, datetime, timedelta

import pytest

from varuna_data_eng.preprocessing.ais_cleaner import AISCleaner
from varuna_data_eng.schemas.ais import GapClass, RawAISPoint
from varuna_data_eng.schemas.provenance import DataProvenance


@pytest.fixture
def dummy_provenance():
    return DataProvenance(source_id="zenodo.123", adapter_id="mock", license="CC-BY")

def test_ais_cleaner_dedup_and_gaps(dummy_provenance):
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    
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
    # Bug fix: the VERY_LONG gap that CAUSED this split (pt3 -> pt4) is now
    # attached to the closing segment (track1) instead of being built and
    # discarded — the split boundary must remain visible in gap metadata.
    assert len(track1.gaps) == 2
    assert track1.gaps[0].gap_class == GapClass.MEDIUM
    assert track1.gaps[1].gap_class == GapClass.VERY_LONG

    track2 = tracks[1]
    assert len(track2.points) == 2 # pt4, pt5
    assert len(track2.gaps) == 1
    assert track2.gaps[0].gap_class == GapClass.SHORT

def test_ais_cleaner_invalid_coords(dummy_provenance):
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    
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


def test_ais_cleaner_does_not_mutate_caller_list(dummy_provenance):
    """Real bug fix: clean() used to call points.sort() in place, silently
    reordering whatever list the caller held a reference to."""
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    pt_a = RawAISPoint(mmsi="1", timestamp=base_time + timedelta(hours=1), lon=0.0, lat=0.0,
                        source="synthetic", provenance=dummy_provenance)
    pt_b = RawAISPoint(mmsi="1", timestamp=base_time, lon=0.0, lat=0.0,
                        source="synthetic", provenance=dummy_provenance)
    original_order = [pt_a, pt_b]
    cleaner.clean(original_order, "1")
    assert original_order == [pt_a, pt_b]  # caller's list untouched


def test_ais_cleaner_flags_do_not_leak_across_split(dummy_provenance):
    """Real bug fix: a SOG/implied-speed anomaly in one segment used to
    remain in the shared `flags` set and get attributed to every later
    segment's track too, once a VERY_LONG-gap split created more than one
    segment. The anomaly must stay scoped to the segment it occurred in."""
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, tzinfo=UTC)

    # Segment 1: a physically implausible SOG (>50kn, non-HSC type) sets a flag.
    pt1 = RawAISPoint(mmsi="1", timestamp=base_time, lon=0.0, lat=0.0,
                       sog_knots=60.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance)
    pt2 = RawAISPoint(mmsi="1", timestamp=base_time + timedelta(minutes=10), lon=0.0, lat=0.0,
                       sog_knots=5.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance)

    # VERY_LONG gap -> forces a split into a clean second segment.
    pt3 = RawAISPoint(mmsi="1", timestamp=base_time + timedelta(hours=30), lon=1.0, lat=1.0,
                       sog_knots=5.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance)
    pt4 = RawAISPoint(mmsi="1", timestamp=base_time + timedelta(hours=30, minutes=10), lon=1.01, lat=1.01,
                       sog_knots=5.0, vessel_type_code=70, source="synthetic", provenance=dummy_provenance)

    tracks = cleaner.clean([pt1, pt2, pt3, pt4], "1")
    assert len(tracks) == 2
    track1, track2 = tracks
    assert "PHYSICALLY_IMPLAUSIBLE_SOG" in track1.quality_flags
    assert "PHYSICALLY_IMPLAUSIBLE_SOG" not in track2.quality_flags  # must not leak forward


def test_ais_cleaner_vessel_type_code_zero_is_unknown_not_other(dummy_provenance):
    """vessel_type_code=0 means 'Not available' per the AIS spec and must map
    to UNKNOWN — not to OTHER, which is what a naive `is not None` fix would
    produce since 0 does not fall in any of the explicit ranges below."""
    from varuna_contracts.schemas import VesselType
    cleaner = AISCleaner()
    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    pt1 = RawAISPoint(mmsi="1", timestamp=base_time, lon=0.0, lat=0.0,
                       vessel_type_code=0, source="synthetic", provenance=dummy_provenance)
    pt2 = RawAISPoint(mmsi="1", timestamp=base_time + timedelta(minutes=10), lon=0.0, lat=0.0,
                       vessel_type_code=0, source="synthetic", provenance=dummy_provenance)
    tracks = cleaner.clean([pt1, pt2], "1")
    assert len(tracks) == 1
    assert tracks[0].vessel_type == VesselType.UNKNOWN
