"""
VARUNA GRID — System configuration report.

M10 (docs/product/HONESTY_LEDGER.md #12). Answers "what is actually
configured in THIS running deployment" per capability, honestly — never
secret values, only REAL / NOT_CONFIGURED plus a plain-English reason. This
is the live source Phase 11's header status pill is meant to read from,
instead of a hardcoded green "Operational" pill.
"""
from fastapi import APIRouter

from apps.api.config import check_startup_config

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/config-report")
def config_report() -> dict:
    return check_startup_config()
