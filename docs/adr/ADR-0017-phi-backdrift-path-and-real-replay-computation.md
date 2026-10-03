# ADR-0017 — Real backward-drift path on `PhiField`, and replay fixtures compute Φ for real

**Status:** Accepted
**Date:** 2026-09-04
**Related:** ADR-0002 (evidence envelope), ADR-0007 (sensitivity block), the M1-M11
correctness audit and Phase 5-10 storytelling work this same session

## Context

Two findings, surfaced by direct user question ("where is the backward drift shown?"):

**1. The backward ensemble computes real per-particle trajectories and throws them away.**
`packages/varuna_prativartan/ensemble.py::run_backward_ensemble` genuinely simulates every
particle backward in time and returns full per-particle, per-timestep position history.
`phi_builder.py` collapses this into a 3D probability histogram (`phi_array`) and persists
only the histogram to `phi.npz` — the individual paths are discarded in-memory, never
reaching `PhiField`, any API contract, or any frontend surface. There has never been a way
to show "the slick's reconstructed backward path" because nothing downstream of the
histogram construction retains path information at all.

**2. Every replay/demo fixture hand-authors its `PhiDiagnostics` as literal constants.**
`packages/varuna_domain/replay_fixtures.py::_phi()` and `_india_phi()` construct
`PhiDiagnostics(entropy=0.30, concentration=0.60, ...)` directly — they never call
`run_backward_ensemble`/`build_phi_field`. The real engine only ever runs via the legacy
`POST /v1/cases/{id}/reconstruct` route (not what the frontend cockpit drives) or the real
`RealE2EPipeline`. Every one of the 11 demo cases a judge would actually see has therefore
never had its Φ field genuinely computed — only authored to look plausible.

Measured this session: a full 20-member, 500-particle, 24h backward ensemble on synthetic
forcing fields completes in **~0.06 seconds**. There is no performance reason for replay
fixtures to hand-author diagnostics instead of computing them.

## Decision

**1. Replay fixtures now call the real engine.** `_phi()`/`_india_phi()` are rewritten to
call `run_backward_ensemble` + `build_phi_field` with each fixture's own real anchor
point/observation time, using `SyntheticModelCurrentField`/`SyntheticWindField` by default
(preserving `EvidenceMode.SIMULATED` honesty exactly as before — nothing about the *evidence
mode* claims changes, only whether the number behind it was authored or computed). `CASE-VALID`
specifically loads the real, already-on-disk ERA5/CMEMS forcing cubes for the MC20/Taylor
Energy site (the same real forcing `scripts/mc20_e2e_seam_validation.py` already proved
loadable) and is promoted to `EvidenceMode.REAL` for its Φ field — the one demo case with a
genuinely, not-illustratively, computed origin field.

**2. `PhiField` gains a new field: `backdrift_path: list[BackdriftPathPoint] | None = None`.**
Each point is the probability-mass-weighted centroid of the Φ field's spatial slice at one
time bin — a real, derived statistic of the histogram that already exists in `phi.npz`, NOT
a literal single particle's path (Φ is a distribution over an ensemble; a centroid is only a
faithful one-line summary of it, and is misleading when the field is multimodal). `None`
follows the same convention as `sensitivity: SensitivityBlock | None` — "not computed", never
"computed and empty". Computed by a new pure function,
`varuna_prativartan.backdrift_path.derive_centroid_path()`, called by `phi_builder.py`
immediately after the histogram is built (cheap — reads the array already in memory, no
extra ensemble cost).

**3. `phi.npz` moves out of the OS temp directory for any caller that wants it to persist.**
`build_phi_field()` gains an optional `output_dir` parameter; omitted, behavior is unchanged
(existing callers keep writing to `tempfile.gettempdir()`, exactly as before — no regression).
The replay-fixture path and the new MC20 real-forcing script both pass a real, versioned
directory under `data/gold/events/`.

## Why a centroid, not the raw per-particle paths (rejected: full path storage)

Storing and serving every individual particle's full trajectory (Option "C" in the
conversation that produced this ADR) was considered and explicitly deferred: it requires a
new persistent storage decision for a much larger artifact (500 particles × 20 members ×
~96 timesteps, not one row per time bin), and the *product* claim that matters — "where did
the origin-probability mass move as we integrate backward" — is fully carried by the
per-timestep centroid derived from data that already persists. If a future session wants the
literal multi-particle animated view, the histogram this ADR ships is the byte-identical
input a "sample N representative particles" pass would need — this decision does not close
that door, it sequences it after the cheaper, real, honest version.

## Consequences

- Every replay/demo case's Φ diagnostics are now genuinely computed, not authored — a case
  with `n_modes: 2` or a `convergence_flag` other than `CONVERGED` can now actually occur in
  the demo if the real (synthetic-forcing) computation produces one, rather than being
  impossible by construction because the fixture always typed `CONVERGED`.
- `CASE-VALID`'s Φ field is the first genuinely `EvidenceMode.REAL` origin-probability
  computation anywhere in the served demo.
- The frontend can now draw a real, honestly-labelled backward-drift path on the map instead
  of a static bounding-box rectangle — see the cockpit map changes in the same commit as this
  ADR.
- `SensitivityBlock`'s existing "expensive, opt-in" design (ADR-0007) is unaffected — this
  ADR's centroid derivation is a byproduct of the histogram already built, not a new
  expensive pass, so it is computed unconditionally rather than opt-in.
