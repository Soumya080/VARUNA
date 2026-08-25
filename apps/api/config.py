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
