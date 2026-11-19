"""Integration test: real AIS data (acquired this pass, MarineCadastre,
2023-01-15, Gulf of Mexico) joined against the real anchor SAR case
(zenodo_p1_00073) using the real find_candidate_tracks() logic.

Skips cleanly if the derived bronze file is absent (it is gitignored raw/
derived data, not committed) — this test documents and exercises the real
join, it does not assert a specific vessel count, since AIS coverage in
this region on this date is genuinely sparse (see
docs/datasets/AIS_ACQUISITION_RECORD.md) and could legitimately be zero.

Key property under test: because zenodo_p1_00073 has no real acquisition
timestamp (Zenodo Part I's known limitation), the join against it MUST
report temporal_join_status="unavailable" — never a fabricated match.
"""
import json
from pathlib import Path

import pytest

from varuna_contracts.schemas import AISPoint, BBox, VesselTrack, VesselType
from varuna_geospatial.ais_join import find_candidate_tracks

REPO_ROOT = Path(__file__).resolve().parents[2]
BRONZE_TRACKS = REPO_ROOT / "data" / "bronze" / "ais" / "gulf_2023-01-15_tracks.json"

# Real bbox, verified via direct rasterio read of the actual file
# (see docs/datasets/AIS_ACQUISITION_RECORD.md).
ANCHOR_CASE_BBOX = BBox(min_lon=-92.141, min_lat=19.371, max_lon=-91.957, max_lat=19.554)


def _load_real_tracks() -> list[VesselTrack]:
    raw = json.loads(BRONZE_TRACKS.read_text())
    tracks = []
    for t in raw:
        points = [
            AISPoint(
                timestamp=p["timestamp"], lon=p["lon"], lat=p["lat"],
                sog_knots=p.get("sog_knots"), cog_deg=p.get("cog_deg"),
                heading_deg=p.get("heading_deg"),
            )
            for p in t["points"]
        ]
        if len(points) < 2:
            continue  # VesselTrack requires >=2 points
        try:
            vessel_type = VesselType(t["vessel_type"])
        except ValueError:
            vessel_type = VesselType.UNKNOWN
        tracks.append(VesselTrack(mmsi=t["mmsi"], imo=t.get("imo"), name=t.get("vessel_name"),
                                    vessel_type=vessel_type, points=points))
    return tracks


@pytest.mark.skipif(not BRONZE_TRACKS.exists(), reason="real AIS bronze data not present (gitignored derived output)")
def test_real_ais_join_reports_unavailable_when_sar_timestamp_missing():
    """zenodo_p1_00073's acquisition_date is a substituted dummy
    (2000-01-01, timestamp_status=unavailable per
    data/manifests/zenodo_part1_manifest.json) — the real timestamp is
    genuinely unknown, so obs_time=None must be passed, never a fabricated
    date, and the result must say so explicitly."""
    tracks = _load_real_tracks()
    result = find_candidate_tracks(ANCHOR_CASE_BBOX, obs_time=None, tracks=tracks,
                                     search_radius_km=50.0)
    assert result.temporal_join_status == "unavailable"
    assert "Spatial-only" in result.provenance_note
    # Every candidate must also individually carry the same caveat.
    for c in result.candidates:
        assert c.temporal_join_status == "unavailable"
        assert c.minutes_from_obs is None


@pytest.mark.skipif(not BRONZE_TRACKS.exists(), reason="real AIS bronze data not present (gitignored derived output)")
def test_real_ais_join_candidates_are_real_provenance_not_synthetic():
    """Whatever candidates (if any) come back must trace to the real
    acquisition — not a mock/synthetic MMSI."""
    tracks = _load_real_tracks()
    result = find_candidate_tracks(ANCHOR_CASE_BBOX, obs_time=None, tracks=tracks,
                                     search_radius_km=200.0)  # generous, since coverage here is sparse
    for c in result.candidates:
        assert not c.mmsi.startswith("MOCK_MMSI")  # never a MockAisAdapter artifact
        assert c.distance_km >= 0


@pytest.mark.skipif(not BRONZE_TRACKS.exists(), reason="real AIS bronze data not present (gitignored derived output)")
def test_real_tracks_load_and_are_well_formed():
    """Sanity check on the acquisition itself: the derived tracks parse as
    valid VesselTrack contract objects."""
    tracks = _load_real_tracks()
    assert len(tracks) > 0
    for t in tracks:
        assert len(t.points) >= 2
        assert all(-180 <= p.lon <= 180 and -90 <= p.lat <= 90 for p in t.points)
