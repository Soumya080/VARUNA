import pytest
from varuna_domain.model_registry import InMemoryModelRegistry, ModelStatus

def test_register_and_retrieve():
    reg = InMemoryModelRegistry()
    mv = reg.register("netra", "mock-v1", "/models/netra_mock.pt", "dataset-v1", {}, "abcdef")
    assert reg.is_registered("netra", "mock-v1")
    assert reg.get_latest("netra").version == "mock-v1"

def test_unregistered_version_returns_none():
    reg = InMemoryModelRegistry()
    assert reg.get_version("netra", "nonexistent") is None
    assert not reg.is_registered("netra", "nonexistent")

def test_model_lifecycle():
    registry = InMemoryModelRegistry()
    
    mv = registry.register("netra", "v1.0", "/models/netra.pt", "v1", {}, "abcdef")
    assert mv.status == ModelStatus.CANDIDATE
    
    # Cannot deploy directly
    with pytest.raises(ValueError):
        registry.update_status("netra", "v1.0", ModelStatus.DEPLOYED)
        
    # Can evaluate
    mv = registry.update_status("netra", "v1.0", ModelStatus.EVALUATED)
    assert mv.status == ModelStatus.EVALUATED
    
    # Cannot approve without approver
    with pytest.raises(ValueError):
        registry.update_status("netra", "v1.0", ModelStatus.APPROVED)
        
    # Approve
    mv = registry.update_status("netra", "v1.0", ModelStatus.APPROVED, approved_by="user1")
    assert mv.status == ModelStatus.APPROVED
    assert mv.approved_by == "user1"
    
    # Deploy
    mv = registry.update_status("netra", "v1.0", ModelStatus.DEPLOYED)
    assert mv.status == ModelStatus.DEPLOYED
    assert mv.deployed_at is not None
