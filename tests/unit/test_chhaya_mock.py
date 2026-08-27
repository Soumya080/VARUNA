import pytest
from datetime import datetime, timezone

from varuna_contracts.schemas import AISPoint, BBox
from varuna_contracts.evidence import EvidenceEnvelope, TrustState, ValidityState, QualityMetrics
from varuna_chhaya.protocol import LatentFinding
from varuna_chhaya.mock import MockChhayaProvider

def _make_test_envelope() -> EvidenceEnvelope:
    from varuna_contracts.evidence import Provenance
    return EvidenceEnvelope(
        artifact_id="test-env-01",
        produced_by="test",
        trust=TrustState.TRUSTED,
        validity_state=ValidityState.VALID,
        quality=QualityMetrics(model_confidence=1.0),
        provenance=Provenance(source_id="test")
    )

def test_insufficient_coverage_returns_no_dark_claim():
    """Threat A-05: sparse AIS coverage must not produce a dark vessel claim."""
    provider = MockChhayaProvider()
    env = _make_test_envelope()
    
    # Large bbox, only 1 AIS point -> coverage will be low
    large_bbox = BBox(min_lon=70, min_lat=10, max_lon=75, max_lat=15)
    single_ais_point = AISPoint(timestamp=datetime.now(timezone.utc), lon=70.0, lat=10.0, sog_knots=10, heading_deg=90)
    
    detections, finding = provider.investigate("scene.tif", [single_ais_point], large_bbox, env)
    assert finding == LatentFinding.INSUFFICIENT_COVERAGE
    assert len(detections) == 0

def test_radar_contact_without_ais():
    """Test RADAR_CONTACT_WITHOUT_AIS: good coverage, no AIS near center"""
    provider = MockChhayaProvider()
    env = _make_test_envelope()
    
    # Bbox around (72.5, 12.5)
    bbox = BBox(min_lon=72.0, min_lat=12.0, max_lon=73.0, max_lat=13.0)
    
    # AIS points all along the edge, providing good coverage but nothing near the center (72.5, 12.5)
    ais_pts = []
    for lat in [12.0, 12.2, 12.8, 13.0]:
        for lon in [72.0, 72.2, 72.8, 73.0]:
            ais_pts.append(AISPoint(
                timestamp=datetime.now(timezone.utc),
                lon=lon, lat=lat, sog_knots=10, heading_deg=0
            ))
            
    detections, finding = provider.investigate("scene.tif", ais_pts, bbox, env)
    assert finding == LatentFinding.RADAR_CONTACT_WITHOUT_AIS
    assert len(detections) == 1
    assert detections[0].is_dark

def test_visible_sources_exist_but_weak():
    """Test VISIBLE_SOURCES_EXIST_BUT_WEAK: good coverage, AIS near center"""
    provider = MockChhayaProvider()
    env = _make_test_envelope()
    
    bbox = BBox(min_lon=72.0, min_lat=12.0, max_lon=73.0, max_lat=13.0)
    
    ais_pts = []
    # Fill the area including the center
    for lat in [12.0, 12.5, 13.0]:
        for lon in [72.0, 72.5, 73.0]:
            ais_pts.append(AISPoint(
                timestamp=datetime.now(timezone.utc),
                lon=lon, lat=lat, sog_knots=10, heading_deg=0
            ))
            
    detections, finding = provider.investigate("scene.tif", ais_pts, bbox, env)
    assert finding == LatentFinding.VISIBLE_SOURCES_EXIST_BUT_WEAK
    assert len(detections) == 0
