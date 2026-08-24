# BACKEND HANDOFF

**Current Branch:** `varuna/backend`
**Current Worktree:** `D:\VARUNA-backend`

## Repository Status
- Worktree is clean.
- Branch `varuna/backend` is up-to-date with `develop` (fast-forwarded to `e8a6186`).
- Accidental copies from the repository root have been safely moved to `D:\VARUNA-setup-backup\`.

## Infrastructure Status
- **Docker Compose:** Broken/Missing. (`docker` command is not recognized in the system).
- **Postgres:** Not running.
- **Redis:** Not running.
- **MinIO:** Not running.

## Database Status
- **Database:** Not running (due to Docker missing).
- **Existing Migrations:** `db/migrations/` exists as a scaffold folder. `alembic.ini` is currently missing. Do not recreate existing structure blindly.

## Python Environment
- **Version:** Python 3.10.4 (Spec requires 3.12, please note this discrepancy).
- **Environment Tool:** `uv` is installed (`0.12.3`).

## Current Backend Files & Scaffold
- `apps/api/` and `apps/worker/` directories exist but are empty (`.gitkeep`).
- `db/migrations/` and `infra/docker/` directories exist.
- `pyproject.toml` contains dependencies for `fastapi`, `celery`, `redis`, `sqlalchemy`, `alembic`.
- **Subsystems Status:**
  - FastAPI: SCAFFOLDED
  - Celery: SCAFFOLDED
  - Redis integration: MISSING (deps exist)
  - PostGIS: MISSING (deps exist)
  - MinIO: MISSING
  - SQLAlchemy: SCAFFOLDED (deps exist)
  - Alembic: SCAFFOLDED (folder exists, ini missing)
  - Source Adapters: SCAFFOLDED (`packages/varuna_source_adapters/`)
  - Data Guard: SCAFFOLDED (`packages/varuna_data_guard/`)
  - PRAMAN: SCAFFOLDED (`packages/varuna_praman/`)
  - Event Spine: SCAFFOLDED (`packages/varuna_pravaah/`)

## Existing Contracts
`packages/varuna_contracts/` contains the authoritative shared contracts (`EvidenceEnvelope`, `PhiField`, `AttributionResultV2`, `ValidityGateResult`, `CaseStateVector`, `MissionFSM`). 
**DO NOT duplicate, modify, or create alternate versions.** If a contract is defective, create an ADR in `docs/adr/` and stop.

## Commands
- **Working commands:** `python --version`, `uv --version`, git commands.
- **Failing commands:** `docker compose` commands (e.g., `docker compose config --services`, `docker compose up -d postgres redis minio`, `docker compose ps`).

## Known Blockers
- `docker` is not installed or not available in PATH, preventing infrastructure startup.
- Python is 3.10 locally (spec requires 3.12).
- `alembic.ini` is missing for database migrations.

## Exact Next Milestone / First Implementation Task
**CASE → EVENT → ARTIFACT → DATA GUARD → AIS PROVIDER → FASTAPI**
*(Do not include scientific algorithm implementation in this handoff)*
