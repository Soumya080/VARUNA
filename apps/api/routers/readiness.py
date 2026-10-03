from fastapi import APIRouter, Depends
from typing import Dict, Any

from apps.api.config import settings
from apps.api.dependencies import get_adapter_registry, get_model_registry
from varuna_source_adapters.service import AdapterRegistry
from varuna_domain.model_registry import InMemoryModelRegistry

router = APIRouter(prefix="/v1/readiness", tags=["ops"])

@router.get("")
def readiness(
    adapters: AdapterRegistry = Depends(get_adapter_registry),
    model_reg: InMemoryModelRegistry = Depends(get_model_registry),
) -> Dict[str, Any]:
    """Provider status matrix. Tells operators what is mock vs real."""
    return {
        "ready": True,
        "demo_mode": settings.demo_mode,
        "providers": {
            "netra": {"status": settings.provider_netra, "version": "mock-v1"},
            "chhaya": {"status": settings.provider_chhaya, "version": "mock-v1"},
            "pravaah": {"status": settings.provider_pravaah, "version": "mock-v1"},
            "abhiyan": {"status": settings.provider_abhiyan, "version": "mock-v1"},
            "smriti": {"status": settings.provider_smriti, "version": "mock-v1"},
        },
        "adapters": adapters.list_adapters(),
        "adapter_health": adapters.health(),
        "models": {
            name: [mv.version for mv in model_reg.list_versions(name)]
            for name in ["netra", "chhaya"]
        },
    }
