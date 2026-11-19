"""
VARUNA GRID — Health Router.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from apps.api.config import settings
from apps.api.dependencies import get_adapter_registry
from varuna_source_adapters.service import AdapterRegistry

router = APIRouter(tags=["health"])

@router.get("/health/deep")
def deep_health(adapters: AdapterRegistry = Depends(get_adapter_registry)):
    adapter_health = adapters.health()
    all_ok = all(adapter_health.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "adapters": adapter_health,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "api_title": settings.api_title,
        "api_version": settings.api_version,
        "demo_mode": settings.demo_mode,
        "scientific_status": settings.scientific_status,
    }

@router.get("/health/dependencies")
def dependencies_health_check():
    from fastapi import HTTPException
    # Simple check for now
    if settings.use_postgres:
        try:
            from varuna_infra.database import get_session_factory
            factory = get_session_factory(settings.database_url)
            with factory() as session:
                from sqlalchemy import text
                session.execute(text("SELECT 1"))
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")
    
    return {"status": "ok", "postgres": settings.use_postgres, "minio": settings.use_minio}
