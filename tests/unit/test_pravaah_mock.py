import pytest
from pathlib import Path
from datetime import datetime, timezone

from varuna_contracts.schemas import SlickDetection, GeoPoint, BBox, SlickClass, ForwardForecast
from varuna_contracts.evidence import EvidenceEnvelope, TrustState, ValidityState, QualityMetrics
from varuna_pravaah.mock import MockPravaahProvider

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

def _make_test_slick(lon: float = 72.0, lat: float = 15.0) -> SlickDetection:
    return SlickDetection(
        slick_id="slick-01",
        scene_id="scene-01",
        observation_time=datetime.now(timezone.utc),
        classification=SlickClass.OIL,
        confidence=0.9,
        mask_path="mock.tif",
        centroid=GeoPoint(lon=lon, lat=lat),
        bbox=BBox(min_lon=lon-0.1, min_lat=lat-0.1, max_lon=lon+0.1, max_lat=lat+0.1),
        area_km2=5.0,
        perimeter_km=10.0,
        elongation=2.0,
        orientation_deg=45.0,
        age_prior_mean_hours=24.0,
        age_prior_std_hours=12.0,
        mean_wind_speed_ms=5.0,
        netra_model_version="mock-v1"
    )

def test_forecast_returns_valid_forward_forecast():
    slick = _make_test_slick()
    env = _make_test_envelope()
    forecast = MockPravaahProvider().forecast_drift(slick, None, 48.0, env)
    ForwardForecast.model_validate(forecast.model_dump())
    assert forecast.horizon_hours == 48.0
    assert Path(forecast.trajectory_path).exists()

def test_landfall_is_interval_not_point():
    # Place slick near Gujarat coast
    slick = _make_test_slick(lon=72.0, lat=21.0)
    env = _make_test_envelope()
    forecast = MockPravaahProvider().forecast_drift(slick, None, 48.0, env)
    
    # Should cross lat 21.0
    assert len(forecast.landfalls) > 0
    # Enforced by pydantic model, hours_until should be positive
    assert forecast.landfalls[0].hours_until > 0
