"""
VARUNA GRID — Database Connection.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create a configured sessionmaker for the given database URL."""
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
