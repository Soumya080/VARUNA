"""Tests for the AIS <-> SAR case temporal/spatial join.

Key property under test: when obs_time is None (SAR timestamp unavailable
— the actual state of Zenodo Part I today), the join must report
temporal_join_status="unavailable" and never silently pretend a temporal
match occurred."""
from datetime import UTC, datetime, timedelta

from varuna_contracts.schemas import AISPoint, BBox, VesselTrack, VesselType
from varuna_geospatial.ais_join import find_candidate_tracks


def _bbox():
    return BBox(min_lon=70.0, min_lat=10.0, max_lon=70.2, max_lat=10.2)


def _track(mmsi: str, lon: float, lat: float, ts: datetime) -> VesselTrack:
    # VesselTrack requires >=2 points; the second point is a few minutes
    # later at (essentially) the same position, which is enough to satisfy
    # the schema without changing what these tests are actually checking
    # (spatial/temporal proximity of the track to a case).
    return VesselTrack(
        mmsi=mmsi,
        vessel_type=VesselType.TANKER,
        points=[
            AISPoint(timestamp=ts, lon=lon, lat=lat, sog_knots=10.0),
            AISPoint(timestamp=ts + timedelta(minutes=10), lon=lon, lat=lat, sog_knots=10.0),
        ],
    )


def test_temporal_join_when_obs_time_present():
    obs_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    near_track = _track("111", 70.1, 10.1, obs_time)  # inside window & radius
    result = find_candidate_tracks(_bbox(), obs_time, [near_track])
    assert result.temporal_join_status == "joined"
    assert len(result.candidates) == 1
    assert result.candidates[0].temporal_join_status == "joined"
    assert result.candidates[0].minutes_from_obs is not None


def test_obs_time_none_yields_unavailable_status():
    near_track = _track("222", 70.1, 10.1, datetime(2026, 1, 1, tzinfo=UTC))
    result = find_candidate_tracks(_bbox(), None, [near_track])
    assert result.temporal_join_status == "unavailable"
    assert len(result.candidates) == 1
    assert result.candidates[0].temporal_join_status == "unavailable"
    assert result.candidates[0].minutes_from_obs is None


def test_track_outside_time_window_excluded():
    obs_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    far_in_time = _track("333", 70.1, 10.1, obs_time - timedelta(hours=100))
    result = find_candidate_tracks(_bbox(), obs_time, [far_in_time],
                                    window_before_hours=48.0, window_after_hours=6.0)
    assert result.candidates == []


def test_track_outside_radius_excluded():
    obs_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    far_in_space = _track("444", 90.0, 30.0, obs_time)
    result = find_candidate_tracks(_bbox(), obs_time, [far_in_space], search_radius_km=50.0)
    assert result.candidates == []


def test_candidates_sorted_by_distance():
    obs_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    far = _track("555", 70.19, 10.19, obs_time)
    near = _track("666", 70.11, 10.11, obs_time)
    result = find_candidate_tracks(_bbox(), obs_time, [far, near])
    assert [c.mmsi for c in result.candidates] == ["666", "555"]


def test_empty_track_list_returns_empty_candidates():
    result = find_candidate_tracks(_bbox(), None, [])
    assert result.candidates == []
    assert result.temporal_join_status == "unavailable"
