import os
import socket
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text as sa_text


@pytest.fixture(scope="session")
def engine():
    """
    Provide a SQLAlchemy engine for integration tests.
    Uses TEST_DATABASE_URL if provided, else falls back to local varuna DB.

    Skips (rather than erroring) when Postgres is not reachable, mirroring
    the socket-probe pattern in tests/integration/test_minio_store.py, so
    the suite degrades gracefully on a machine with no docker-compose stack
    running instead of failing every dependent test with a connection error.
    """
    database_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://varuna:varuna@localhost:5432/varuna",
    )
    # Use psycopg instead of psycopg2 as per pyproject.toml
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+psycopg://")

    parsed = urlparse(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect((host, port))
        except OSError:
            pytest.skip(f"Postgres not available at {host}:{port}")

    try:
        eng = create_engine(database_url)
        with eng.connect() as conn:
            conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()
    except Exception as e:
        pytest.skip(f"Postgres not available for testing: {e}")

    yield eng
    eng.dispose()
