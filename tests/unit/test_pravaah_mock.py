import pytest
from pathlib import Path
from datetime import datetime, timezone

from varuna_contracts.schemas import SlickDetection, GeoPoint, BBox, SlickClass, ForwardForecast
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, TrustState, ValidityState, QualityMetrics
from varuna_pravaah.mock import MockPravaahProvider

def _make_test_envelope() -> EvidenceEnvelope:
    from varuna_contracts.evidence import Provenance
    return EvidenceEnvelope(
        artifact_id="test-env-01",
        produced_by="test",
        trust=TrustState.TRUSTED,
        validity_state=ValidityState.VALID,
        quality=QualityMetrics(model_confidence=1.0),
        provenance=Provenance(source_id="test"),
        mode=EvidenceMode.SIMULATED,
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

def test_forecast_envelope_is_simulated_even_when_input_envelope_claims_real():
    """
    ADR-0009. MockPravaahProvider fabricates trajectories from a fixed
    drift+noise model, not from real forcing -- its output must be
    SIMULATED regardless of what mode the caller's input envelope carries.
    `.derive()` can only ever worsen mode, so if this provider naively
    derived from a REAL-mode input, the fabricated forecast would
    incorrectly inherit a REAL claim. This is the regression this test
    guards against.
    """
    slick = _make_test_slick()
    real_env = EvidenceEnvelope(
        artifact_id="real-env-01", produced_by="test",
        provenance=_make_test_envelope().provenance, mode=EvidenceMode.REAL,
    )
    forecast = MockPravaahProvider().forecast_drift(slick, None, 24.0, real_env)
    assert forecast.envelope.mode is EvidenceMode.SIMULATED
    assert forecast.envelope.case_id == real_env.case_id
    assert real_env.artifact_id in forecast.envelope.parent_artifact_ids


def test_landfall_is_interval_not_point():
    # Place slick near Gujarat coast
    slick = _make_test_slick(lon=72.0, lat=21.0)
    env = _make_test_envelope()
    forecast = MockPravaahProvider().forecast_drift(slick, None, 48.0, env)
    
    # Should cross lat 21.0
    assert len(forecast.landfalls) > 0
    # Enforced by pydantic model, hours_until should be positive
    assert forecast.landfalls[0].hours_until > 0
