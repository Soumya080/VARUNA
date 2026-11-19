# ADR-0005: MinIO for Large Scientific Objects

## Status
Accepted

## Context
VARUNA GRID v2 produces large scientific objects during its pipeline, most notably the `PhiField` from the NYAYA and PRATIVARTAN services. A PhiField can contain hundreds of thousands of particle trajectories, making it unsuitable for a traditional relational database (like PostgreSQL) due to BLOB size and retrieval overhead.

## Decision
We will use **MinIO** (S3-compatible object storage) for storing large binary objects (PhiFields, serialized NumPy arrays, etc.) and implement an `ObjectStore` port to interface with it.

## Rationale
1. **Size efficiency**: S3 is optimized for immutable, large binary blobs.
2. **Local/Air-gapped compatibility**: MinIO runs as a local Docker container and provides an exact S3-compatible API, meaning our code can run fully locally in air-gapped environments, and trivially scale to AWS S3 in production.
3. **Immutability**: Scientific evidence (Phi) is immutable once generated, fitting the WORM (Write Once Read Many) nature of S3.

## Consequences
- The system must coordinate writes between Postgres (metadata) and MinIO (data).
- **Rule**: MinIO write MUST succeed before the Postgres metadata record is committed.
- Storage classes and bucket provisioning must be managed via `docker-compose.yml`.
