# Indian Ocean incident fixtures (Phase 5/6)

**Product decision, 2026-09-03:** case scenarios beyond the single real MC20
(Gulf of Mexico) validation case are **curated, historically-researched
static fixtures** — not a live news-headline API. Rationale: no new external
dependency or secret, historically accurate and citable, and reliable at
demo time (a live feed can rate-limit or drift mid-demonstration). This
mirrors the codebase's existing discipline against fabricating live evidence
— a headline-derived "case" would blur exactly the REAL/SIMULATED line every
other fixture in this repository is careful to keep sharp.

## What exists

`packages/varuna_domain/replay_fixtures.py`:
- `FIXTURE_NAMES` (6) — the original MC20/Gulf-of-Mexico-anchored fixtures.
  **Unchanged.** Still the one real external-validation-comparable dataset.
- `INDIA_FIXTURE_NAMES` (5) — new, curated Indian Ocean incidents:

| Fixture | Models (real event) | Region |
|---|---|---|
| `IND-CASE-01` | 2017 BW Maple / Dawn Kanchipuram collision | Chennai/Ennore coast |
| `IND-CASE-02` | 2010 MSC Chitra – MV Khalijia III collision | Mumbai harbour |
| `IND-CASE-03` | 2021 MV X-Press Pearl disaster | Off Colombo, Sri Lanka |
| `IND-CASE-04` | 2020 MT New Diamond fire | Sri Lanka east coast |
| `IND-CASE-05` | Illustrative ONGC Mumbai High platform-source scenario (not a vessel collision) | Mumbai High offshore field |

- `ALL_FIXTURE_NAMES` — both sets, for anywhere a picker needs the full list.

## Honesty discipline (same as every other fixture in this repo)

- Every stage's `evidence_mode` is `SIMULATED`, never `REAL` — enforced and
  tested (`tests/unit/test_india_replay_fixtures.py::
  test_every_stage_is_simulated_never_real`).
- Coordinates/dates/vessel identity are real where publicly documented
  (BW Maple, MSC Chitra, X-Press Pearl, New Diamond); flagged as a
  plausible-format placeholder where the real MMSI isn't independently
  verified public record (see each scenario's `source_note`).
- Detection/Φ/attribution numeric parameters (area_km2, posterior, etc.) are
  explicitly illustrative reconstructions, not measured data — stated in
  every `source_note`.
- `IND-CASE-05` deliberately has no vessel identity (`vessel_mmsi=
  "000000000"`, `vessel_name="UNKNOWN (platform source)"`) — it's a
  platform-sourced scenario, and inventing a vessel to attribute it to would
  be a fabrication, not an illustration.

## UI categorization (per the explicit user decision this session)

Both sets stay **always visible, in clearly separate sections** — never
hidden, never merged, never presented as interchangeable:
- Indian Ocean incidents lead/default.
- The original six are relabelled "External Validation — MC20 (Gulf of
  Mexico)" wherever a fixture is offered for selection, since MC20 remains
  the one case built on real Sentinel-1 data rather than a reconstruction.

`GET /v1/replay/fixtures` reflects this directly: `fixtures` (all 11),
`india_incidents` (the 5), `global_validation` (the original 6) — a picker
can group on those two labelled lists without re-deriving the split.

## Adding another incident

Add one `_IndiaScenario` entry to `_INDIA_SCENARIOS` in
`replay_fixtures.py` (own anchor/bbox/time/vessel/rationale — never touch
`_ANCHOR`/`_BBOX`/`_T_OBS`, which are the original six's shared constants).
Write a `source_note` citing what's real vs. illustrative, matching the
existing five's standard. Add a test row to
`tests/unit/test_india_replay_fixtures.py` (parametrized — most tests need
no per-fixture change) plus a manual fact-check of the cited event before
merging.
