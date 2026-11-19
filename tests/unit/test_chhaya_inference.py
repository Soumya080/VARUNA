import pytest
from datetime import datetime, timezone
import uuid
from varuna_chhaya.inference import ChhayaInferenceService
from varuna_infra.model_loader import ModelLoader
from varuna_domain.model_registry import InMemoryModelRegistry, ModelStatus
from varuna_contracts.schemas import SlickDetection, SlickClass

def test_chhaya_inference_forecast():
    registry = InMemoryModelRegistry()
    registry.register("chhaya", "v1", "path/to", "ds", {}, "c1")
    registry.update_status("chhaya", "v1", ModelStatus.EVALUATED)
    registry.update_status("chhaya", "v1", ModelStatus.APPROVED, approved_by="usr1")
    
    loader = ModelLoader(registry)
    service = ChhayaInferenceService(loader, "v1")
    
    detection = SlickDetection(
        slick_id=str(uuid.uuid4()),
        scene_id="s1",
        observation_time=datetime.now(timezone.utc),
        classification=SlickClass.OIL,
        confidence=0.9,
        mask_path="p",
        centroid={"lon": 0.5, "lat": 0.5},
        bbox={"min_lon": 0.0, "min_lat": 0.0, "max_lon": 1.0, "max_lat": 1.0},
        area_km2=10.0,
        perimeter_km=4.0,
        elongation=1.0,
        orientation_deg=0.0,
        age_prior_mean_hours=12.0,
        age_prior_std_hours=2.0
    )
    
    pred = service.forecast(detection, None)
    assert pred.forecast_id == "forecast_1"
    assert pred.horizon_hours == 72.0
