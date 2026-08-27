import pytest
from varuna_netra.inference import NetraInferenceService
from varuna_infra.model_loader import ModelLoader, UnregisteredModelError
from varuna_domain.model_registry import InMemoryModelRegistry, ModelStatus
from varuna_contracts.evidence import EvidenceEnvelope

def test_netra_inference_requires_approved_model():
    registry = InMemoryModelRegistry()
    registry.register("netra", "v1", "path/to/model", "dsv1", {}, "commit1")
    loader = ModelLoader(registry)
    
    with pytest.raises(UnregisteredModelError):
        NetraInferenceService(loader, "v1")
        
    registry.update_status("netra", "v1", ModelStatus.EVALUATED)
    with pytest.raises(UnregisteredModelError):
        NetraInferenceService(loader, "v1")
        
    registry.update_status("netra", "v1", ModelStatus.APPROVED, approved_by="user1")
    # Now it should work
    service = NetraInferenceService(loader, "v1")
    assert service.get_model_version() == "v1"
    
def test_netra_inference_detect():
    registry = InMemoryModelRegistry()
    registry.register("netra", "v1", "path/to/model", "dsv1", {}, "commit1")
    registry.update_status("netra", "v1", ModelStatus.EVALUATED)
    registry.update_status("netra", "v1", ModelStatus.APPROVED, approved_by="user1")
    
    loader = ModelLoader(registry)
    service = NetraInferenceService(loader, "v1")
    
    envelope = EvidenceEnvelope(
        case_id="case1",
        artifact_id="art1",
        produced_by="test_runner",
        provenance={"source_id": "test"}
    )
    detections = service.detect("scene.tiff", "wind.nc", envelope)
    
    assert len(detections) == 1
    assert detections[0].netra_model_version == "v1"
