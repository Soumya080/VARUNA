# CODEBASE_SUMMARY.md
# AUTO-GENERATED CONTEXT FILE — saves tokens on re-exploration
# Last updated: 2026-08-24T20:37 IST

## Repository: d:\SIH-26 (VARUNA GRID v2)

## Architecture Flow
```
NETRA (SAR detection) → PRATIVARTAN (backward ensemble) → PhiField (3D histogram)
→ NYAYA (path integral scoring + posterior) → Validity Gate → AttributionResultV2
```

## Python Environment
- **Target**: Python 3.12 | **Dev machine**: Python 3.10.4
- **Workaround**: `sweep_runner.py` monkeypatches `datetime.UTC` and `enum.StrEnum` for 3.10 compat
- Key deps: numpy, scipy, pydantic v2, tqdm

## Package Layout (`packages/`)
| Package | Status | Purpose |
|---|---|---|
| `varuna_contracts` | **LOCKED, VERIFIED** (22 tests) | All Pydantic schemas, envelopes, states |
| `varuna_geospatial` | **VERIFIED** | haversine, bbox, point-to-segment |
| `varuna_prativartan` | **IMPLEMENTED (M2)** | Backward advection ensemble + PhiField construction |
| `varuna_nyaya` | **IMPLEMENTED (M2)** | Path integral, prior, latent, posterior, validity gate |
| `varuna_domain` | SCAFFOLDED | Domain services |
| `varuna_netra` | SCAFFOLDED | SAR oil-spill detection (needs torch) |
| Others | SCAFFOLDED | chhaya, pravaah, abhiyan, missions, alerts, praman, smriti |

## Key Contract Types (DO NOT MODIFY)
| Type | Module | Key Fields |
|---|---|---|
| `EvidenceEnvelope` | evidence.py | artifact_id, produced_by, **provenance: Provenance**, trust, validity_state, derive() |
| `PhiField` | phi.py | phi_id, data_path (.npz), bbox, diagnostics, sensitivity, envelope |
| `PhiDiagnostics` | phi.py | entropy, **concentration**, effective_support_km2, convergence_flag, **n_modes**, **ensemble_members_completed/requested** |
| `TimeDistribution` | phi.py | **time_edges_unix**, mass, **mode_unix**, **p05_unix**, **p95_unix** |
| `SensitivityBlock` | phi.py | age/forcing/diffusivity/weathering_sensitivity (dominant_assumption is @property) |
| `AttributionResultV2` | decision.py | candidates: list[CandidateScore], latent_probability, **latent_finding: LatentFinding**, decision_state, distinguishability, posterior_entropy, **n_candidates_screened/scored** |
| `CandidateScore` | decision.py | mmsi, path_integral, prior: PriorContribution, likelihood, posterior, **rank (ge=1)**, closest_approach_km, phi_mass_explained |
| `ValidityGateResult` | decision.py | case_id, state, checks, blocking_reasons, officer_visible_caveats, envelope |
| `VesselTrack` | schemas.py | mmsi, vessel_type: VesselType, points: list[AISPoint] (min_length=2), **total_gap_minutes is @property** |
| `AISPoint` | schemas.py | timestamp, lon, lat, **sog_knots**, **heading_deg** (NOT speed/heading) |
| `VesselType` | schemas.py | TANKER, CARGO, FISHING, PASSENGER, TUG, OTHER, UNKNOWN |
| `AssetType` | schemas.py | DORNIER, OPV, STATION_BOAT (coast guard assets, NOT vessel types) |

## Contract Gotchas (learned the hard way)
1. `EvidenceEnvelope` constructor **requires** `provenance=Provenance(source_id=...)`, not `validity=` or `lineage=`
2. `VesselTrack.total_gap_minutes` is a **computed @property**, not a constructor arg
3. `AISPoint` fields are `sog_knots` / `heading_deg`, NOT `speed` / `heading`
4. `CandidateScore.rank` has `ge=1` — must be set at construction, not mutated after
5. All `_Base` models use `extra="forbid"` — any extra kwargs cause ValidationError
6. `PhiDiagnostics.ensemble_completeness` is a computed @property from `ensemble_members_completed / ensemble_members_requested`
7. `SensitivityBlock.dominant_assumption` is a computed @property, not a field
8. `TimeDistribution` uses unix seconds, not hours — phi_builder must convert
9. Python 3.10 compat: `datetime.UTC` and `enum.StrEnum` don't exist — use monkeypatch runner

## Experiment Structure
```
experiments/go_nogo/     — INVALID (v1, do not use)
experiments/go_nogo_v2/  — M2 valid harness
  ├── config.py          — GoNoGoConfig (pydantic)
  ├── truth.py           — generate_case() with forward advection + hard negatives
  ├── baselines.py       — naive_distance_baseline, uncalibrated_prativartan_baseline
  ├── harness.py         — run_case(): PRATIVARTAN → NYAYA → Validity Gate
  ├── metrics.py         — compute_metrics() from results list
  ├── sweep.py           — run_sweep(): loops over cases
  ├── sweep_runner.py    — monkeypatch runner for Python 3.10
  ├── report.py          — markdown report generator
  └── visualize.py       — matplotlib plots (6 chart types)
```

## Test Structure
```
tests/contract/  — 22 passing tests (evidence envelope, backend compat)
tests/robustness/ — test_m2_pipeline.py (M2 integration test)
```

## Running Commands (PowerShell)
```powershell
# Run contract tests (works on 3.10 only with monkeypatch — they import decision.py which uses UTC)
$env:PYTHONPATH="packages"; python -m pytest tests/contract -q

# Run M2 sweep
$env:PYTHONPATH="packages;."; python experiments/go_nogo_v2/sweep_runner.py
```

## Authoritative Files
- `LLM_IMPLEMENTATION_GUIDE.md` — architecture, invariants, honesty rules
- `SETUP_STATUS.md` — what exists vs what doesn't
- `docs/DECISIONS.md` — rationale for discarding v1 go/no-go
- `FAILURE_THREAT_MATRIX.md` — 27 P0 threats
