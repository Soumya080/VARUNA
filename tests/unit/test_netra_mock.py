import pytest
import numpy as np
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from varuna_contracts.schemas import SlickDetection, SlickClass, GeoPoint, BBox
from varuna_contracts.evidence import EvidenceEnvelope, EvidenceMode, TrustState, ValidityState, QualityMetrics, DegradationState, AnomalyFlag
from varuna_netra.mock import MockNetraProvider
from varuna_netra.service import NetraService

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

def test_mock_returns_valid_slick_detections():
    provider = MockNetraProvider(seed=42, n_detections=2)
    envelope = _make_test_envelope()
    detections = provider.detect("dummy/scene.tif", None, envelope)
    assert len(detections) == 2
    for d in detections:
        # Round trip to ensure it's valid according to Pydantic contract
        SlickDetection.model_validate(d.model_dump())
        assert d.netra_model_version == "mock-v1"
        assert d.age_prior_std_hours > 0

def test_mock_low_wind_reduces_confidence():
    # Write a wind .npz with u10=1.0, v10=1.0 (speed ~1.4 m/s)
    temp_dir = Path(tempfile.gettempdir()) / "varuna_tests"
    temp_dir.mkdir(parents=True, exist_ok=True)
    wind_path = temp_dir / "low_wind.npz"
    np.savez(wind_path, u10=np.array([1.0]), v10=np.array([1.0]))
    
    provider = MockNetraProvider(seed=42)
    envelope = _make_test_envelope()
    detections = provider.detect("scene.tif", str(wind_path), envelope)
    assert len(detections) > 0
    assert detections[0].confidence < 0.5
    assert detections[0].classification == SlickClass.AMBIGUOUS

def test_service_derives_envelope():
    service = NetraService(MockNetraProvider(seed=42, n_detections=1))
    parent_env = _make_test_envelope()
    detections, env = service.detect_slicks("scene.tif", None, parent_env, "CASE-TEST")
    assert env.produced_by == "netra"
    assert env.artifact_id == "netra-CASE-TEST"
    assert env.trust.rank >= parent_env.trust.rank  # never upgrades

def test_service_derives_envelope_with_low_wind_degradation():
    temp_dir = Path(tempfile.gettempdir()) / "varuna_tests"
    temp_dir.mkdir(parents=True, exist_ok=True)
    wind_path = temp_dir / "low_wind.npz"
    np.savez(wind_path, u10=np.array([1.0]), v10=np.array([1.0]))
    
    service = NetraService(MockNetraProvider(seed=42, n_detections=1))
    parent_env = _make_test_envelope()
    detections, env = service.detect_slicks("scene.tif", str(wind_path), parent_env, "CASE-TEST")
    
    assert env.degradation_state == DegradationState.PARTIAL_INPUT_LOSS
    assert AnomalyFlag.PHYSICALLY_IMPLAUSIBLE in env.anomaly_flags
