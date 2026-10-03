from fastapi import APIRouter, Depends
from varuna_domain.prahari.service import PrahariService

# We need a dependency for PrahariService
def get_prahari_service() -> PrahariService:
    from varuna_domain.prahari.mock import MockPrahariProvider
    from varuna_domain.prahari.service import PrahariService
    return PrahariService(provider=MockPrahariProvider(), netra_service=None, workflow=None)

router = APIRouter(prefix="/v1/prahari", tags=["prahari"])

@router.get("/status")
def status(svc: PrahariService = Depends(get_prahari_service)):
    return {"running": svc.is_running}
