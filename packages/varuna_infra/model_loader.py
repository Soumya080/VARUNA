from typing import Any
from varuna_domain.model_registry import ModelRegistry, ModelStatus

class UnregisteredModelError(Exception):
    pass

class ModelLoader:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        
    def load(self, model_name: str, version: str) -> Any:
        entry = self.registry.get_version(model_name, version)
        if entry is None or entry.status not in (ModelStatus.APPROVED, ModelStatus.DEPLOYED):
            raise UnregisteredModelError(f"Model {model_name} version {version} is not approved or deployed.")
        
        # Stub for actual model loading, e.g., torch.load
        class LoadedMockModel:
            def __init__(self, artifact_path):
                self.artifact_path = artifact_path
            def __call__(self, x):
                return x
                
        return LoadedMockModel(entry.artifact_path)
