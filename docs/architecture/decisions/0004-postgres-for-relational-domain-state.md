# ADR-0004: PostgreSQL for Relational Domain State

## Status
Accepted

## Context
VARUNA GRID v2 requires a persistent, relational store for managing Case metadata, Case lifecycle state (CaseStatus, ScientificStatus), Domain Events for the Event Spine, and lightweight Artifact metadata (Praman). The previous version used in-memory stores, which is sufficient for M2 but not for the M3.5 productized backend.

## Decision
We will use **PostgreSQL 16** via SQLAlchemy (v2.0+) and Alembic for all relational domain state.

## Rationale
1. **ACID Compliance**: Ensures strong consistency for state transitions, event log sequence, and artifact metadata.
2. **Ecosystem**: SQLAlchemy provides an excellent Unit of Work (Session) pattern to implement our Repository interfaces smoothly.
3. **Air-gappability**: Postgres runs cleanly as a single Docker container, fulfilling the DEMO_MODE/air-gapped requirement.
4. **Relational guarantees**: Cases, Events, and Artifacts have strictly relational invariants (Events belong to Cases, etc.).

## Consequences
- Requires Alembic for database migrations.
- Tests will require a Postgres instance or an SQLite in-memory fallback (though SQLite might miss Postgres-specific JSONB features).
- The `EventSpine` will persist events to a Postgres table (`events`) instead of an in-memory list.
