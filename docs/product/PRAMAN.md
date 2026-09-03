# PRAMAN — Provenance & Evidence Guarantee

**Status: REAL**, implemented as two complementary modules, not one. When any
product doc, UI label, or PDF report text says "PRAMAN," it refers to both of
these together.

## 1. Artifact registry — `packages/varuna_praman/praman.py::PramanService`

What it does: `register_artifact()` / `get()` / `list_by_case()` / `verify()`
— a content-hashed (sha256) registry of every artifact a case produces.
`verify()` recomputes the digest and reports whether an artifact still
matches what was registered.

Storage: `InMemoryArtifactRepository` by default; a real
`PostgresArtifactRepository` (`packages/varuna_infra/postgres_repos.py`,
per ADR-0004) when `settings.use_postgres` is set — see
`apps/api/dependencies.py::get_artifact_repo()`.

What it does **not** do: reason about *how* evidence relates to other
evidence — that's the ledger's job (below).

## 2. Evidence ledger — `packages/varuna_evidence/ledger.py::EvidenceLedger`

What it does: the case's evolving evidence graph. Two rules enforced
structurally, not by convention:

- **Revision never destroys.** `revise()` supersedes an item; the prior
  version stays in the ledger (marked `SUPERSEDED`), pointing at its
  replacement.
- **Contradiction is recorded, not resolved.** The ledger stores that two
  items disagree; it never picks a winner — that judgement stays with
  NYAYA/the Validity Gate, which have the scientific contracts for it.

Used by `packages/varuna_integration/intelligence.py::ledger_from_run()` /
`CaseIntelligenceService` to build a per-case evidence trail from pipeline
stage results.

## Why two modules, one name

They were built in different work sessions under different package names
(`varuna_praman` predates `varuna_evidence`), and a later research pass
initially proposed building an "Evidence Ledger" as if it didn't exist yet —
it already did, just not under the PRAMAN name. Renaming/merging them was
considered and rejected: it would touch every import site in
`varuna_integration/intelligence.py` and its tests for a purely cosmetic
gain. The fix is this document plus the cross-reference docstrings on both
modules, not a code migration.

## What "PRAMAN is real" means, precisely

- Every artifact a case produces is content-hashed and independently
  verifiable (`praman.py`).
- The evidence graph behind a case's conclusions is queryable and
  tamper-evident — nothing is silently overwritten, contradictions are
  visible, not hidden (`ledger.py`).
- Neither module fabricates a hash, a revision, or a resolution.
