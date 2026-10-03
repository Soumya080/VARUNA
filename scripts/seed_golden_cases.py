"""
VARUNA GRID — Seed Golden Cases.

Loads the golden case fixtures and inserts them into the database.
"""
import asyncio
from varuna_infra.database import create_session_factory
from apps.api.config import settings
from tests.fixtures.case_0001 import generate_case_0001
from varuna_domain.entities import Case, CaseStatus
from varuna_infra.postgres_repos import PostgresCaseRepository

async def seed():
    print("Seeding Golden Cases...")
    if not settings.use_postgres:
        print("Settings indicate use_postgres is False, skipping DB seed.")
        return

    session_factory = create_session_factory(settings.database_url)
    repo = PostgresCaseRepository(session_factory)
    
    # CASE 0001
    print("Generating CASE-0001...")
    data = generate_case_0001()
    
    case_0001 = Case("CASE-0001")
    case_0001.status = CaseStatus.CREATED
    repo.save(case_0001)
    
    # We would also seed events, artifacts, vessels, tracks here if this script was fully fleshed out
    
    print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed())
