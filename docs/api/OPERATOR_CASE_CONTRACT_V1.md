# VARUNA GRID v2 — Operator Case Contract (v1)

## Purpose

`OperatorCase` is the canonical, versioned, read-only representation of one
VARUNA case handed from the backend to the future operator dashboard. It is
a **projection**, not a second business-logic layer: every field is either
copied verbatim from a real, already-typed backend contract, or is an
explicit "not produced / blocked / unavailable" marker. It never computes
science, infers a missing value, or overrides provenance or validity.

```
REAL BACKEND STATE  →  CANONICAL OPERATOR VIEW  →  FRONTEND
```

## Scope

This document covers:

- `packages/varuna_contracts/operator_case.py` — the typed contract
- `apps/api/operator_case_view.py` — the adapter (`Case` → `OperatorCase`)
- `GET /v1/cases/{case_id}/operator-view` — the read-only endpoint
- `tests/contract/test_operator_case.py` — contract tests

It does **not** implement the operator dashboard UI, mutate anything, or
touch NETRA, Track 2 scientific calculations, or raw/Gold datasets. Track 2's
ratified sensitivity normalization ([ADR-0007](../adr/ADR-0007-phi-sensitivity-design.md))
and `EvidenceMode`/`GateReason` ([ADR-0006](../adr/ADR-0006-provenance-mode-and-reason-codes.md))
are consumed here exactly as Track 2 defined them.

## Schema version

`OperatorCase.schema_version` is always `"v1"` (`OPERATOR_CASE_SCHEMA_VERSION`
in `operator_case.py`) and is part of the JSON payload itself — a consumer
never has to infer the contract version from the URL. See "Backward
compatibility" below.

## Endpoint

```
GET /v1/cases/{case_id}/operator-view
```

Read-only. Returns 404 (`CaseNotFoundError`) if the case does not exist.
Adapts the project's existing router conventions (`apps/api/routers/cases.py`)
— it is not a parallel API. The pre-existing `/v1/cases/{id}`, `/phi`,
`/attribution`, `/validity`, `/artifacts` endpoints are unchanged and remain
available; `operator-view` is additive.

## The two status vocabularies

**Do not conflate these.** They answer different questions and are kept as
separate fields throughout the contract.

| Vocabulary | Question it answers | Type |
|---|---|---|
| `EvidenceMode` | Is this evidence a real measurement, a simulated stand-in, or absent? | `varuna_contracts.evidence.EvidenceMode` (`real` / `simulated` / `unavailable`) |
| `ProducerStatus` | Has the backend stage that would fill this section actually run for this case yet? | `varuna_contracts.operator_case.ProducerStatus` (`not_yet_produced` / `produced` / `blocked` / `error`) |

A section can be `NOT_YET_PRODUCED` regardless of what `EvidenceMode` its
inputs would eventually carry — e.g. PRAVAAH forecasting is a real, wired
subsystem (`varuna_pravaah.service.PravaahService`), but
`CaseWorkflow` (`packages/varuna_domain/case_workflow.py`) never calls it as
part of the per-case pipeline. That is a `ProducerStatus` fact, not an
`EvidenceMode` fact — reporting `forecast.evidence_mode = UNAVAILABLE` would
have been a category error, so it is `None` instead and the
`ProducerStatus.NOT_YET_PRODUCED` + `reason` explain why.

`EvidenceMode` itself is never invented here — every `evidence_mode` value on
this contract is read off an existing `EvidenceEnvelope.mode` already
attached to the underlying object (`PhiField.envelope`,
`AttributionResultV2.envelope`, `ValidityGateResult.envelope`), or is `None`
where no envelope exists yet for that section (see field guide below).

Case-level workflow state (`SystemStatusView.case_status`) reuses the
repository's own existing vocabulary, `varuna_domain.entities.CaseStatus`
(`created` / `ingesting` / `guarding` / `reconstructing` / `attributing` /
`evaluating` / `completed` / `failed` / `quarantined`) — no third, competing
status enum was invented for this contract.

## No fake defaults

Every optional value is wrapped in a `SectionEnvelope[T]`:

```python
class SectionEnvelope(BaseModel, Generic[T]):
    status: ProducerStatus
    reason: str | None = None
    evidence_mode: EvidenceMode | None = None
    value: T | None = None
```

`status`/`reason` are always populated, even when `value` is `None` — a
frontend never has to guess "why is this empty?" from silence. Within
`EvidenceHealthView.components`, `score` is `None` (not `0`) whenever no
real score has been computed, with `status`/`reason` explaining why.

## Sections

Where a canonical typed contract already exists for a subsystem's output,
`OperatorCase` reuses it directly inside a `SectionEnvelope` rather than
redefining an equivalent shape (per the "prefer adapters over redefining
domain objects" instruction). New types were added only for genuine gaps.

| Section | Value type | Reused existing contract? |
|---|---|---|
| `observation` | `ObservationView` (new) | No canonical "raw case input" contract exists in the current pipeline; see below |
| `detection` | `SlickDetection` | Yes — `varuna_contracts.schemas.SlickDetection` (NETRA's own output type) |
| `origin` | `PhiField` | Yes — `varuna_contracts.phi.PhiField` (includes `diagnostics`, `sensitivity` per Track 2) |
| `ais` | `list[AISCandidateView]` (new, bounded) | Adapter over `varuna_contracts.schemas.VesselTrack` — summarized, not the full point list |
| `attribution` | `AttributionResultV2` | Yes — `varuna_contracts.decision.AttributionResultV2` |
| `validity` | `ValidityGateResult` | Yes — `varuna_contracts.decision.ValidityGateResult` (serialized verbatim; the API never re-runs gate logic) |
| `forecast` | `ForwardForecast` | Yes — `varuna_contracts.schemas.ForwardForecast` |
| `decision` | `list[AssetTasking]` | Yes — `varuna_contracts.schemas.AssetTasking` |
| `mission` | `list[MissionRecord]` | Yes — `varuna_contracts.states.MissionRecord` (existing Mission FSM) |
| `alerts` | `list[AlertView]` (new adapter) | Adapts `varuna_alerts.protocol.DeliveryResult` (a dataclass) into a pydantic view |

### `observation`

Summarizes what `CaseWorkflow.ingest()` actually received
(`n_slick_points`, `n_tracks`, `obs_time_hours`, a derived `bbox`). There is
currently no canonical "raw SAR observation" contract wired into the
per-case pipeline — ingest takes already-extracted slick points directly, not
a scene/product object — so this section reports what genuinely exists
rather than inventing sensor metadata (product ID, polarization, platform)
nobody supplied. `evidence_mode` is `None` here: the current ingest path
carries no `EvidenceEnvelope` of its own to read a mode from.

### `detection`

Reuses `SlickDetection` verbatim. **Currently always `NOT_YET_PRODUCED`** in
practice: NETRA scene inference is not wired into `CaseWorkflow` (see
"Missing Backend Producers" below) — `reason` reports
`NETRA_INFERENCE_NOT_WIRED_INTO_CASE_PIPELINE` explicitly rather than
returning an empty-looking object.

### `origin`

Reuses `PhiField` verbatim, including Track 2's `diagnostics` (honest Φ
quality: `convergence`, `n_modes`, `particles_lost`, `ensemble_completeness`,
...) and `sensitivity` (Track 2's ratified `SensitivityBlock`, `None` unless
the caller ran `PrativartanService.reconstruct_origin_with_sensitivity()`).
`evidence_mode` is `phi.envelope.mode` — read, never re-derived.

### `ais`

`AISCandidateView` is a bounded summary (mmsi, vessel type, point/gap
counts, time span) — the full AIS point-by-point trajectory is **not**
embedded (see "Performance"). This is AIS **observation** only. NYAYA's
attribution posterior for a given vessel lives in `attribution.candidates`,
never here — the two are kept structurally separate per the task's explicit
instruction not to conflate AIS observation with NYAYA attribution.

### `attribution` / `validity`

Both are the real typed objects, unmodified. `validity` in particular is
**never** recomputed at the API layer — the API serializes whatever
`ValidityService.evaluate()` already decided. `SectionEnvelope.status` for
`validity` is `PRODUCED` when `gate.allows_operational_action` is true and
`BLOCKED` otherwise — this reuses the gate's own `allows_operational_action`
property rather than re-implementing gate policy.

### `forecast` / `decision` / `mission` / `alerts`

All four have real, implemented backend services
(`varuna_pravaah.service.PravaahService`, `varuna_abhiyan.service.AbhiyanService`,
`varuna_missions.service.MissionService`, `varuna_alerts.service.AlertService`)
— but **none of them are called by `CaseWorkflow`** as part of the per-case
pipeline today, and `mission`/`alerts` additionally have no case-scoped
lookup path available to the adapter (`MissionService`/`AlertService` keep
state that isn't indexed by `case_id` in a way `CaseWorkflow` exposes). All
four sections are therefore always `NOT_YET_PRODUCED` today, each with a
`reason` naming the specific gap — this is `ProducerStatus`, not evidence
quality, and is expected to flip to `PRODUCED` once each stage is wired into
the pipeline (see "Remaining Backend Producers").

### `evidence` (`EvidenceHealthView`)

One `EvidenceComponentView` row per dashboard evidence-strip item (`sar`,
`ais`, `model_consistency`, `forcing`). Every `score` is either a real,
already-computed `[0,1]` quantity reused from elsewhere in the contract
(e.g. `forcing.score = phi.diagnostics.ensemble_completeness`, an existing
Track 2 diagnostic) or `None` with a `reason` — `model_consistency` is
always `None`/`NOT_YET_PRODUCED` because **no cross-model consistency check
is implemented anywhere in the current backend**; inventing one here would
be exactly the kind of fabrication this contract exists to prevent.

### `provenance`

`case_id`, the list of PRAMAN artifact IDs and their `produced_by` source
IDs for this case, and the `evidence_manifest` artifact ID if one has been
sealed. No credentials, tokens, or storage endpoints are ever included.
`model_versions`/`processing_versions` are currently empty dicts —
`CaseWorkflow` does not query a model-version registry per case today (see
"Remaining Backend Producers").

### `system_status`

`case_status` / `scientific_status` reuse `varuna_domain.entities.CaseStatus`
/ `ScientificStatus` values directly.

## Backward compatibility

- Existing endpoints (`/v1/cases/{id}`, `/phi`, `/attribution`, `/validity`,
  `/artifacts`, ...) and their response shapes are unchanged.
- `operator-view` is purely additive.
- `schema_version` is in the payload; a `v2` would be a new literal value
  and (if the shape changes incompatibly) a new endpoint or a version
  query/header — never a silent reshape of `v1` responses.
- New fields on `v1` should be additive (`Optional`, defaulted) wherever
  practical; removing or retyping an existing `v1` field is a breaking
  change and requires a version bump, not a patch to this document alone.

## Performance

`OperatorCase` never embeds full SAR rasters, full AIS point tracks, raw Φ
arrays, or forcing cubes. Heavy artifacts stay behind their existing
references: `PhiField.data_path` (an `.npz` key, not inlined),
`AISCandidateView` (a bounded per-vessel summary), and PRAMAN
`artifact_id`s in `provenance.artifact_ids` for anything that needs to be
fetched separately.

## Security

No field on this contract ever carries API keys, tokens, passwords, or raw
storage credentials — `ProvenanceView` exposes IDs and version strings only.
**Note:** `apps/api/middleware/auth.py`'s `AuthMiddleware` is currently a
stub (no real authentication/RBAC exists in this codebase yet). This
contract does not invent a second authorization system to compensate — it
assumes whatever auth the API gains later applies uniformly, the same way it
already would to the existing `/v1/cases/*` endpoints.

## Examples

See `docs/api/examples/operator_case_example.json` — three cases
(`REAL_SCIENTIFIC_SECTIONS`, `PARTIAL`, `BLOCKED`), all built from actual
`OperatorCase.model_validate()`-checked payloads. **Every numeric value in
these examples is either a genuine output of the tiny fixture-scale smoke
run they were generated from, or an explicit synthetic placeholder — none
are hand-typed to resemble real MC20 results.** Do not mistake fixture-scale
smoke numbers (tiny particle/ensemble counts) for production-scale science;
see Track 2's own "IMPLEMENTATION SMOKE — NOT SCIENTIFIC RESULT" convention.

## Frontend field mapping (documentation only — no UI built here)

```
Top bar:      observation.value.obs_time_hours, origin.value.spatial_modes[0].centroid,
              validity.value.state, detection.value.confidence
Map:          detection.value.mask_path / bbox, origin.value (Phi heatmap via data_path),
              ais.value[*], forecast.value.landfalls
Right panel:  detection.value (summary), attribution.value.candidates (ranked),
              evidence.components
Bottom:       system_status, decision.value, mission.value, alerts.value
```

Every one of those accesses must check `.status == PRODUCED` first — no
field in `OperatorCase` is safe to dereference unconditionally.

## Remaining backend producers (must land before a complete real MC20 case can render)

1. **NETRA inference wired into `CaseWorkflow`** — currently the pipeline
   starts from pre-extracted slick points; `detection` is always
   `NOT_YET_PRODUCED`.
2. **Real AIS via `SourceAdapter`/`fetch_with_mode()`** — real AIS ingestion
   exists only as standalone scripts (`scripts/ingest_real_ais*.py`), not
   wired through the adapter boundary Track 2 built
   (`varuna_source_adapters.protocol.fetch_with_mode`).
3. **PRAVAAH/ABHIYAN/Mission/Alerts wired into `CaseWorkflow`** — all four
   subsystems exist and are independently callable but are not invoked as
   part of the per-case pipeline, and `mission`/`alerts` additionally need a
   case-scoped lookup path exposed to the adapter.
4. **A per-case model-version registry query** — `provenance.model_versions`
   is currently always empty; `varuna_domain.model_registry.InMemoryModelRegistry`
   exists but `CaseWorkflow` never queries it per case.
5. **Real RBAC/authentication** — `AuthMiddleware` is a stub; this contract
   does not gate on roles today because nothing in the codebase does yet.

None of the above were implemented in this task — implementing them would
have gone beyond "build the stable contract" into modifying Track 2 science,
NETRA, or the data track, which this task explicitly excludes.
