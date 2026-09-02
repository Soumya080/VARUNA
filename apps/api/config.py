"""
VARUNA GRID — API Configuration.
"""
from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings

class VarunaSettings(BaseSettings):
    # API metadata
    api_title: str = "VARUNA GRID API"
    api_version: str = "3.5.0"

    # Mode
    demo_mode: bool = False
    use_postgres: bool = False           # False = in-memory by default
    use_minio: bool = False              # False = local dict-backed by default
    
    # Providers
    provider_netra: str = "mock"
    provider_chhaya: str = "mock"
    provider_pravaah: str = "mock"
    provider_abhiyan: str = "mock"
    provider_adapters: str = "mock"
    provider_smriti: str = "mock"

    # Alert channels
    alert_channels: list[str] = ["console"]   # "console" | "mock_sms" | "mock_sachet"
    alert_dedupe_window_seconds: int = 300

    # Authentication
    # INTERIM DEFAULT, stated plainly: this is a development secret, not a
    # production one. No login/token-issuing service exists in this repo yet
    # (see apps/api/security.py), so there is nothing that mints real
    # user-attributable tokens today. Any deployment outside a trusted
    # network MUST override this via the JWT_SECRET_KEY env var (no prefix
    # is configured on this settings class) before accepting a Bearer token
    # as authoritative.
    jwt_secret_key: str = "dev-insecure-secret-change-before-any-real-deployment-32bytes-min"
    jwt_algorithm: str = "HS256"
    # STEP 7: bounded lifetime for tokens issued by POST /v1/auth/login.
    access_token_expire_minutes: int = 30

    # Infrastructure
    database_url: Optional[str] = None
    redis_url: Optional[str] = None
    minio_endpoint: Optional[str] = None
    minio_access_key: Optional[str] = None
    minio_secret_key: Optional[str] = None
    minio_bucket: str = "varuna"
    minio_secure: bool = False
    
    # Scientific Status (Hardcoded, NOT configurable)
    @property
    def scientific_status(self) -> str:
        return "EXPERIMENTAL / UNVALIDATED"

    @model_validator(mode='after')
    def validate_infrastructure(self):
        if self.use_postgres and not self.database_url:
            raise ValueError("database_url MUST be configured when use_postgres is true")
        if self.use_minio and not (self.minio_endpoint and self.minio_access_key and self.minio_secret_key):
            raise ValueError("MinIO configuration MUST be present when use_minio is true")
        return self

settings = VarunaSettings()
