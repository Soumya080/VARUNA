import pytest
import os
from sqlalchemy import create_engine

@pytest.fixture(scope="session")
def engine():
    """
    Provide a SQLAlchemy engine for integration tests.
    Uses TEST_DATABASE_URL if provided, else falls back to local varuna DB.
    """
    database_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://varuna:varuna@localhost:5432/varuna"
    )
    # Use psycopg instead of psycopg2 as per pyproject.toml
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        
    eng = create_engine(database_url)
    
    # Ensure postgis extension exists
    with eng.connect() as conn:
        conn.execute(org_sa_text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()

    yield eng
    eng.dispose()

from sqlalchemy import text as org_sa_text
