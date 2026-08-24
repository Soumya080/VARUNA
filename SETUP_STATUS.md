# SETUP_STATUS.md
## VARUNA GRID v2 — what actually exists, verified against the repository

**Generated:** 24 Aug 2026 · **Method:** direct file inspection + executed tests.
**This file is the authority on implementation status.** README and design documents
describe intent. When they disagree with this file, this file wins.

### Status labels

| Label | Meaning |
|---|---|
| **VERIFIED** | Exists, imports, and has a passing test executed in this repo |
| **IMPLEMENTED** | Code exists and is complete, no test executed yet |
| **SCAFFOLDED** | Directory/stub only — no working code |
| **INTEGRATION-READY** | Interface defined; real backend unavailable to us |
| **MOCKED / SIMULATED** | Deliberately fake; must be labelled as such in the UI |
| **PLANNED** | Designed, not started |
| **BLOCKED** | Cannot proceed until a dependency clears |

---

## 1. VERIFIED

| Artifact | Evidence |
|---|---|
| `packages/varuna_contracts/evidence.py` | `EvidenceEnvelope`, trust vocabulary, Bounded Evidence Influence. 22 contract tests pass. |
| `packages/varuna_contracts/states.py` | 4-axis case state, `check_case_invariants`, mission FSM with authorization gate. Tested. |
| `packages/varuna_contracts/phi.py` | Structured `PhiField` + diagnostics + sensitivity. Imports clean. |
| `packages/varuna_contracts/decision.py` | `AttributionResultV2`, `ValidityGateResult`, `DecisionState`, `LatentFinding`. Imports clean. |
| `packages/varuna_contracts/schemas.py` | v1 domain payloads (detections, AIS, forecasts, tasking). Imports clean. |
| `packages/varuna_geospatial/utils.py` | haversine, bbox, destination point, point-to-segment. Executed. |
| `tests/contract/test_evidence_envelope.py` | **22 passed** — influence ceilings, monotonic degradation, case invariants, mission FSM authorization |
| `pyproject.toml` | Python 3.12, setuptools `package-dir` → `packages/`. Install verified via PYTHONPATH. |

**Contract invariants proven by executed tests:**
- influence weight cannot exceed its trust ceiling (all four states)
- `derive()` never upgrades trust, validity, or degradation (property-based, Hypothesis)
- lineage and anomaly flags merge across multiple inputs
- content hashing is order-independent and stable
- only VALID/DEGRADED reach the Action Gateway
- an asset cannot be committed on a non-dispatchable outcome
- an outcome cannot precede attribution
- a case cannot close without preserved evidence
- `ASSIGNED` is impossible without `human_approved_by`
- illegal mission transitions are rejected; `CLOSED` is terminal

---

## 2. IMPLEMENTED (untested)

| Artifact | Note |
|---|---|
| `infra/docker/Dockerfile` | API/worker image. **Not yet built** — needs a docker build run. |
| `infra/docker/Dockerfile.physics` | OpenDrift via micromamba. **Not yet built.** |
| `docker-compose.yml` | Rewritten; now references a real Dockerfile. **Not yet started.** |
| `Makefile` | Full target set. Some targets reference files that do not exist yet. |
| `.github/workflows/ci.yml` | Not yet run — no remote configured. |
| `src/common/{config,logging}.py` | v1 location. **Pending migration** to `packages/`. |

---

## 3. SCAFFOLDED (directory + docstring only — no working code)

All of these are empty packages awaiting their owner:

```
packages/varuna_domain          varuna_data_guard      varuna_source_adapters
packages/varuna_netra           varuna_chhaya          varuna_pravaah
packages/varuna_abhiyan         varuna_missions        varuna_alerts
packages/varuna_praman          varuna_smriti
apps/api                        apps/worker            apps/web
db/migrations                   infra/{nginx,monitoring,scripts}
tests/{unit,integration,scientific,robustness,e2e}
experiments/{convergence,weathering,forcing_bias,ais_robustness,multimodality,data_guard,baselines}
```

**Partial scientific pipeline implementation complete.** PRATIVARTAN and NYAYA are implemented (M2). NETRA, 
CHHAYA, PRAVAAH, ABHIYAN, PRAMAN, SMRITI are all directories.

---

## 4. INVALID — do not use

| Artifact | Problem |
|---|---|
| `experiments/go_nogo/` | **Runs, but the harness cannot fail.** Reports 100% top-1 at 24 h / 20 vessels. Verified defects: innocent vessels drawn a median 33 km from origin; guilty track ends 18 h before observation so the baseline can never win; `L₀` fixed at `1/(2N+1)`; backward ensemble centred on the exact truth field; true slick age passed in. Rebuilt fairly → **~12% top-1** (chance = 5%). See `docs/DECISIONS.md` §1 and `FAILURE_THREAT_MATRIX.md` §8. |
| `experiments/go_nogo/results/quick_test/` | Outputs of the invalid harness. Do not publish, do not calibrate on. |
| `experiments/go_nogo/results/full_sweep/` | **Empty** — the full sweep has never been run. |

**Go/no-go status: NOT ESTABLISHED.** ROLE 01 days 1–3.

---

## 5. INTEGRATION-READY (interface defined, real backend unavailable)

| Capability | Reality |
|---|---|
| Indian operational AIS | Restricted/commercial. Adapter interface planned; demo uses synthetic traffic drawn from real US distributions. **PS explicitly permits this — label it.** |
| Government command systems | No access. Adapter interface only. |
| SACHET / CAP alerting | Interface planned. Never describe as live. |
| WhatsApp / SMS delivery | Provider interface planned; no credentials. |
| National-scale persistent watch | PRAHARI architecture supports it; prototype is historical replay over a scoped region. |
| Native mobile client | Not built. Field mode is responsive web. |

---

## 6. SIMULATED (must carry a visible label)

- Indian EEZ AIS traffic
- Government command-system responses
- WhatsApp/SMS delivery confirmations
- Live field telemetry from assets
- National deployment posture

Every simulated provider must set `is_simulated=True` and render a `SIMULATED` badge
(threat L-04). Presenting any of these as live is a P0 honesty violation.

---

## 7. BLOCKED

| Item | Blocked by | Owner |
|---|---|---|
| Physics implementation | OpenDrift not installed (`ModuleNotFoundError` confirmed) | ROLE 04 → ROLE 01 |
| Any stack execution | Docker images never built | ROLE 04 |
| NETRA training | Datasets not downloaded (Zenodo ~45 GB, ESSD) | ROLE 01 |
| Real forcing | No Copernicus/CMEMS/CDS accounts registered | ROLE 02 |
| Real AIS | MarineCadastre CSV not downloaded | ROLE 02 |
| Calibration | Go/no-go harness invalid — cannot fit on invalid sweep (threat N-06) | ROLE 01 |
| CI execution | No git remote configured | ROLE 04 |

---

## 8. Environment reality check

| Item | Spec | Actual | Action |
|---|---|---|---|
| Python | 3.12 | **3.10.4** on the dev machine | Upgrade, or run in Docker |
| OpenDrift | required | **not installed** | ROLE 04 day 1 |
| torch | required for NETRA | not installed | ROLE 01 before day 5 |
| Docker | required | not verified | ROLE 04 day 1 |
| git remote | needed for CI | **none configured** | ROLE 04 |
| Uncommitted work | — | v2 restructure is staged, not committed | commit before branching |

---

## 9. Threat-matrix coverage

| | Count | Tested |
|---|---|---|
| P0 threats | 27 | **4** (O-01, O-02, O-05, O-06) |
| P1 threats | 20 | 0 |

Remaining 23 P0 threats are PLANNED. Each must have a passing robustness test before the
finale — see `FAILURE_THREAT_MATRIX.md`.

---

## 10. Immediate commands

```bash
# 1. Verify the contract package (works today)
PYTHONPATH=packages python -m pytest tests/contract -q      # → 22 passed

# 2. Install the project properly
pip install -e ".[dev]"

# 3. Bring up infrastructure (after ROLE 04 builds the image)
make up-infra
make migrate

# 4. Fast test loop
make test

# 5. Full quality gate
make check
```

---

## 11. Next action per role — start here

| Role | Do this first | Why |
|---|---|---|
| **ROLE 01** Scientific/ML | `packages/varuna_nyaya/mock_phi.py` — synthetic `PhiField` + `.npz` in the locked format. **Before lunch, day 1.** | ROLE 03 and ROLE 04 are blocked without it |
| **ROLE 02** Data/Backend | `apps/api/{db,models}.py` — PostGIS schema with `Geography` columns, then `main.py` health check | Everything persists through you |
| **ROLE 03** Frontend/Geo | Scaffold `apps/web` (Vite+TS+Tailwind+MapLibre), render OpenFreeMap basemap, then `PhiHeatmapLayer` on ROLE 01's mock | Fully parallel; never blocked |
| **ROLE 04** MLOps/Ops | Build the Docker image and **verify OpenDrift backward simulation runs** | Two hard blockers on the critical path |

Read `LLM_IMPLEMENTATION_GUIDE.md` + your `tasks/ROLE_0N_*.md` before writing code.

---

## 12. Honest summary

The **architecture and contracts are real and tested**. The trust model, the state
machine, and both safety gates are enforced in code with 22 passing tests.

**The system is not implemented.** Every scientific module is an empty directory, no
service has ever started, and the one experiment that exists produces a number that
cannot be used.

That is an accurate day-0 position for a seven-day build, and it is a considerably better
one than a repository that *claims* completion it cannot demonstrate.
