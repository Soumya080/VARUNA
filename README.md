<p align="center">
  <img src="https://img.shields.io/badge/SIH_2026-PS_SIH26143-1f6f8b?style=for-the-badge" alt="SIH 2026" />
  <img src="https://img.shields.io/badge/Organisation-NTRO-a8412a?style=for-the-badge" alt="NTRO" />
  <img src="https://img.shields.io/badge/Python-3.12-2f6b54?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/Architecture-v2_trust--aware-6a3d7a?style=for-the-badge" alt="v2" />
  <img src="https://img.shields.io/badge/Status-early_implementation-b58a2e?style=for-the-badge" alt="Status" />
</p>

<h1 align="center">VARUNA GRID</h1>
<h3 align="center">National Marine Pollution Watch &amp; Response Grid</h3>

<p align="center">
  <em>Oil spill detection · probabilistic vessel attribution · trust-aware maritime enforcement</em>
</p>

---

> **Status honesty.** The architecture and contracts are implemented and tested (22
> passing contract tests). **The scientific pipeline is not implemented** — every module
> is currently a scaffolded package. The one experiment in the repository produces a
> number that cannot be used. `SETUP_STATUS.md` is the authority; this README describes
> intent and design.

---

## Contents

- [The problem](#the-problem) · [What VARUNA does](#what-varuna-does) · [RDPA](#the-mechanism--rdpa)
- [Trust-aware architecture](#trust-aware-architecture) · [Modules](#modules) · [Stack](#tech-stack)
- [Repository](#repository) · [Setup](#setup) · [Tests](#tests) · [Evaluation](#evaluation)
- [Failure behaviour](#failure-behaviour) · [Real vs simulated](#real-vs-simulated)
- [Seven-day sprint](#seven-day-sprint) · [Honesty rules](#honesty-rules) · [Status](#current-status) · [Roadmap](#roadmap)

---

## The problem

> **PS SIH26143** — *Leveraging satellite imagery to determine oil spills at sea along with
> AIS data correlations to identify the vessel responsible for the spill.* — **NTRO**

A ship opens a valve at night, sixty nautical miles offshore. The bilge discharge damps
the capillary waves that scatter radar, so it shows up as a dark patch when a satellite
next passes — hours or days later. By then the slick has drifted and deformed, and the
ship is a hundred nautical miles away.

**Oil is a drifting, deforming record of a crime whose timestamp and location have been
erased by the ocean.** Every deployed tool identifies the culprit by looking at where the
evidence *ended up*, rather than reconstructing where it *began*.

### Why India

| Factor | Detail |
|---|---|
| **Geography** | Astride the Gulf → Malacca tanker artery. ~7,500 km coastline. |
| **Revisit gap** | Sentinel-1 revisit over the Indian EEZ is days, not hours. **India's default case is the aged slick** — precisely where geometric matching fails. |
| **Institutional gap** | ITOPF's India profile documents no satellite attribution capability. (No *publicly documented* system — not a claim that none exists.) |

---

## What VARUNA does

It inserts the missing inferential step between "a slick exists" and "a human decides",
and closes a feedback loop that currently does not exist.

```
OBSERVE → TRUST → DETECT → RECONSTRUCT → ATTRIBUTE → FORECAST
       → PRIORITIZE → ASSIGN → AUTHORIZE → RESPOND → VERIFY → PRESERVE → LEARN
```

**Core design principle:**

> No untrusted information should silently become a trusted decision.

**The product is the API**, not the map. Strip the UI and what remains is a service that
ingests `(SAR scene, timestamp, AIS window)` and returns a calibrated posterior over
vessels, a serialised origin probability field, and an evidence manifest.

---

## The mechanism — RDPA

**Reverse-Drift Posterior Attribution** with a latent dark-vessel hypothesis.

Instead of *"which ship is lying alongside this slick?"*, reconstruct **where and when the
oil was released** as a probability field, then score every candidate by how much of that
field its trajectory actually explains.

```
1  SEGMENT      slick → contour, area, elongation, AGE PRIOR (a distribution)
2  ADVECT BACK  N particles × M structurally-varied forcing members, negative timestep
3  ACCUMULATE   origin probability field  Φ(x, y, t)  + convergence/mode/sensitivity diagnostics
4  PATH INTEGRAL   L_k = ∫ Φ(x_k(t), y_k(t), t) dt   × behavioural prior π_k
5  LATENT L₀    residual Φ mass no observed track explains
6  NORMALISE    calibrated posterior over {L₀, π₁L₁ … π_kL_k}
7  GATE         distinguishability + validity → STRONG_LEAD | WEAK_LEAD
                | NOT_DISTINGUISHABLE | LATENT_SOURCE | INCONCLUSIVE
```

**Why this formulation:** it is the only one that degrades gracefully with slick age. As
the origin field widens, probabilities spread and the system *says so*, instead of
confidently naming the nearest innocent ship.

Two distinctions v1 collapsed and v2 keeps separate:

- **Trust ≠ confidence.** Trust is about the source; confidence is about the measurement.
- **Peakedness ≠ distinguishability.** Two vessels inside one lobe of Φ can produce a sharp
  posterior and still be inseparable. That returns `NOT_DISTINGUISHABLE`, not a name.

---

## Trust-aware architecture

Three planes. Full detail with sequence and state diagrams in **[`ARCHITECTURE_V2.md`](ARCHITECTURE_V2.md)**.

```
GOVERNANCE   Event Spine · PRAMAN · audit · lineage · observability · versioning
                                    ▲ every step emits
DATA         External → Source Adapter → Ingestion Gate → DATA GUARD
             → Flow Inspection → NETRA → PRATIVARTAN → Φ diagnostics
             → NYAYA ← CHHAYA → ★ VALIDITY GATE ★ → PRAVAAH → Case Intelligence
             → ABHIYAN → Mission FSM → ★ AUTHORIZATION ★ → HUMAN → Action Gateway
             → Field Outcome → SMRITI
                                    ▲ governed by
CONTROL      source trust · policy · thresholds · RBAC · versions · model registry
```

The two ★ gates are mandatory chokepoints. No path to an operational action bypasses them.

**Bounded Evidence Influence.** Each observation carries `0 ≤ w ≤ 1`, capped by its trust
state (TRUSTED 1.0 · DEGRADED 0.6 · CONFLICTED 0.3 · QUARANTINED 0.0). The **value is
never modified** — only its downstream influence is bounded. A legitimately extreme
observation survives; a compromised source is contained. This is *not* PPO clipping.

**Uncertainty propagates structurally.** `EvidenceEnvelope.derive()` refuses to produce an
output more trusted, more valid, or less degraded than its worst input.

---

## Modules

| Module | Role | Status |
|---|---|---|
| **PRAHARI** | Persistent EEZ watch — scheduler, scene discovery, triage | SCAFFOLDED |
| **Data Guard** | Trust boundary — schema, units, CRS, freshness, cross-source, manipulation | SCAFFOLDED |
| **NETRA** | Slick detection + look-alike rejection + age **distribution** | SCAFFOLDED |
| **PRATIVARTAN** | Reverse-advection ensemble → Φ with first-class diagnostics | SCAFFOLDED |
| **NYAYA** | Path-integral scoring, priors, latent hypothesis, calibrated posterior | SCAFFOLDED |
| **CHHAYA** | Dark-vessel investigation (xView3). Distinguishes *no visible source* from *weak visible sources* | SCAFFOLDED |
| **PRAVAAH** | Forward drift → landfall **interval**, exposure | SCAFFOLDED |
| **ABHIYAN** | Feasibility filter → value matrix → exact assignment → explanation | SCAFFOLDED |
| **Missions** | Mission FSM + authorization gate | **VERIFIED** (contracts) |
| **Alerts** | Materiality → role router → policy → freshness → channel | SCAFFOLDED |
| **PRAMAN** | Evidence preservation, deterministic manifests, hashing | SCAFFOLDED |
| **SMRITI** | History, recurrence, corridors, **human-gated** retraining pipeline | SCAFFOLDED |

---

## Tech stack

**Backend** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · httpx · Celery · Redis
**ML** PyTorch · TorchGeo · segmentation-models-pytorch · scikit-learn · XGBoost · MLflow
**Geospatial** GDAL · rasterio · rioxarray · xarray · GeoPandas · Shapely · PyProj
**SAR** ESA SNAP · pyroSAR **Physics** OpenDrift / OpenOil
**Data** PostgreSQL + PostGIS · MinIO
**Frontend** React · TypeScript · Vite · MapLibre GL · deck.gl · TanStack Query · Zustand · Tailwind · SSE
**Ops** Docker Compose · Nginx · OpenTelemetry · Prometheus · Grafana · Loki
**Security** JWT · RBAC · Argon2 · Bandit · pip-audit · Trivy
**Testing** pytest · Hypothesis · contract / integration / scientific / robustness / e2e

Deliberately absent: Kafka, Kubernetes, service mesh, vector DB, RAG, agent framework, RL
in the core. Each requires an ADR to reintroduce.

---

## Repository

```
packages/varuna_contracts/     ★ THE locked contract — import from here, never redefine
packages/varuna_{domain,data_guard,source_adapters,geospatial}/
packages/varuna_{netra,prativartan,nyaya,chhaya,pravaah,abhiyan}/
packages/varuna_{missions,alerts,praman,smriti}/
apps/{api,worker}/                         frontend/VARUNA-frontend_yash/   ← the real UI (Next.js)
tests/{unit,contract,integration,scientific,robustness,e2e}/
experiments/{go_nogo,convergence,forcing_bias,baselines,...}/
infra/{docker,nginx,monitoring,scripts}/   db/migrations/   docs/{architecture,adr,runbooks}/
tasks/ROLE_01..04                          models/  data/{raw,bronze,silver,gold}/
```

**Key documents**

| File | Purpose |
|---|---|
| [`SETUP_STATUS.md`](SETUP_STATUS.md) | **Authority on what is implemented** |
| [`LLM_IMPLEMENTATION_GUIDE.md`](LLM_IMPLEMENTATION_GUIDE.md) | Universal context packet for any coding LLM |
| [`ARCHITECTURE_V2.md`](ARCHITECTURE_V2.md) | Full architecture, diagrams, trust boundaries |
| [`FAILURE_THREAT_MATRIX.md`](FAILURE_THREAT_MATRIX.md) | 47 threats → containment → degraded behaviour → test |
| [`BUILD_PLAN_7_DAYS.md`](BUILD_PLAN_7_DAYS.md) | Day-by-day, four roles, acceptance criteria |
| [`ML_TRAINING_GUIDE.md`](ML_TRAINING_GUIDE.md) · [`COMPUTE_SPEC.md`](COMPUTE_SPEC.md) | Training manual · hardware plan |
| [`tasks/ROLE_0N_*.md`](tasks/) | Self-contained per-person context |

---

## Setup

**Prerequisites:** Python 3.12, Docker + Compose, conda (for OpenDrift).

```bash
git clone <repo> && cd varuna-grid
cp .env.example .env          # fill in Copernicus / CDS credentials

pip install -e ".[dev]"       # core + dev tooling
pip install -e ".[ml]"        # optional: torch, smp, mlflow
conda install -c opendrift -c conda-forge opendrift   # physics

make up-infra                 # postgres + redis + minio
make migrate
make test                     # → 22 passed
```

Run the API locally against the infra stack:

```bash
uvicorn apps.api.main:app --reload --port 8000
```

Full stack in Docker: `make up`. Frontend: `docker compose --profile web up`.

> **Note:** `apps/api` is scaffolded — the server does not serve routes yet. `make test`
> works today.

---

## Tests

```bash
make test              # unit + contract — fast, no services
make test-integration  # needs make up-infra
make test-scientific   # seeded numerical regression
make test-robustness   # failure injection per the threat matrix
make test-e2e          # full pipeline on CASE-0001
make check             # lint + typecheck + fast tests (what CI runs)
```

Contract tests encode the architectural invariants. **A contract-test failure means an
architectural rule was broken, not that a test is flaky.**

---

## Evaluation

**North-star KPI:** top-1 attribution accuracy at 24-hour slick age with ≥20 vessels in
the envelope, subject to ECE < 0.05.

| Axis | Measures |
|---|---|
| Accuracy vs slick age | 2 / 6 / 12 / 24 / 48 h |
| Accuracy vs traffic density | 5 / 20 / 50 / 100+ vessels |
| **Calibration** | ECE + reliability diagram — the number no competing team will report |
| Latent-source detection | P/R with the guilty track deleted; false-latent rate when present |
| Perception | IoU/F1 on Zenodo; **look-alike FP rate reported separately** |
| Ablations | ensemble vs single · path-integral vs nearest-point · ±prior · ±latent · ±wind channel |

**Baselines:** nearest vessel · Cerulean-style geometric (parity/proximity/temporality) ·
single deterministic backtrack.

> ⚠️ **The current go/no-go harness is invalid.** It reports 100% top-1, but it cannot
> fail — innocent vessels sit a median 33 km from the origin, the guilty track ends before
> the observation so the baseline can never win, and L₀ is a constant. Rebuilt fairly:
> ~12% (chance = 5%). No number leaves `experiments/` until the validity checklist in
> [`FAILURE_THREAT_MATRIX.md`](FAILURE_THREAT_MATRIX.md) §8 passes.

---

## Failure behaviour

Full matrix in [`FAILURE_THREAT_MATRIX.md`](FAILURE_THREAT_MATRIX.md) — 27 P0 and 20 P1
threats, each with a containment location and a required test.

| Failure | System behaviour |
|---|---|
| Forcing outage | Cache → snapshot → climatology; `FALLBACK_SOURCE`, trust DEGRADED, uncertainty widened, banner shown |
| Schema/unit/CRS drift | Batch quarantined, raw retained, case blocked — **never silently coerced** |
| Correlated source bias | Combined influence reduced; ensemble spread widened |
| AIS spoofing | Kinematic implausibility → track down-weighted; latent hypothesis absorbs residual |
| Ensemble non-convergence | `NOT_CONVERGED` → validity RESTRICTED → no vessel named |
| Multimodal Φ | Both lobes drawn and labelled competing origins |
| Flat posterior | `INCONCLUSIVE` — still emits a narrowed search box |
| Two vessels in one lobe | `NOT_DISTINGUISHABLE` — both listed, neither named |
| Weak evidence + dispatch attempt | Blocked by validity gate **and** case invariants |
| Any assignment | Blocked without `human_approved_by` |

**INCONCLUSIVE is a first-class result.** An enforcement tool that always names someone is
worse than useless.

---

## Real vs simulated

| REAL | INTEGRATION-READY | SIMULATED |
|---|---|---|
| Scientific core, SAR processing | Indian operational AIS | Indian EEZ AIS traffic |
| Benchmark datasets (Zenodo, ESSD, xView3) | Government command systems | Government responses |
| Model inference, PostGIS, MinIO | SACHET / CAP alerting | WhatsApp / SMS delivery |
| Assignment logic, Event Spine, PRAMAN | WhatsApp / SMS providers | Live field telemetry |
| Docker deployment, monitoring | National watch expansion | National deployment |

Every simulated provider carries `is_simulated=True` and renders a **SIMULATED** badge.
Presenting one as live is a P0 honesty violation.

---

## Seven-day sprint

| Day | Focus |
|---|---|
| 1 | Foundation — contracts, Docker, CI, PostGIS, mock Φ, frontend scaffold |
| 2 | PRATIVARTAN + Φ + AIS ingest + Data Guard |
| 3 | NYAYA + posterior + calibration + baselines |
| 4 | NETRA + CHHAYA + validity gate + ABHIYAN |
| 5 | PRAVAAH + missions + alerts + PRAMAN |
| 6 | PRAHARI + adapters + SMRITI + retraining pipeline |
| 7 | **Integration, failure testing, deployment, rehearsal — no new features** |

Four roles: [Scientific/ML](tasks/ROLE_01_SCIENTIFIC_ML.md) ·
[Data/Backend](tasks/ROLE_02_DATA_BACKEND.md) ·
[Frontend/Geo](tasks/ROLE_03_FRONTEND_GEO.md) ·
[MLOps/Ops](tasks/ROLE_04_MLOPS_OPS.md)

---

## Honesty rules

Non-negotiable. Enforced in review and in [`LLM_IMPLEMENTATION_GUIDE.md`](LLM_IMPLEMENTATION_GUIDE.md) §12.

- Attribution is **not** unsolved — Cerulean and CleanSeaNet ship it in production.
- Backward drift tracing is **not** our innovation — the PS asks for it; HELCOM Seatrack
  has done it for ~20 years.
- **Ours is the probabilistic formulation:** ensemble uncertainty, origin probability
  field, path-integral scoring, latent-source hypothesis, calibration, distinguishability,
  and trust-aware operational decisioning.
- Simulated evaluation ≠ operational validation.
- Indian AIS is synthetic — say so on the slide.
- Never "patentable" (only *potentially patent-relevant*). Never "real-time" (Sentinel-1
  revisit is days — that constraint is *why* backward inference exists). Never "no Indian
  system exists" as fact (say *no publicly documented system*).
- The system never names a ship without human sign-off. It produces ranked, calibrated
  leads for an overflight — not verdicts.

---

## Current status

**24 Aug 2026** — see [`SETUP_STATUS.md`](SETUP_STATUS.md) for the verified breakdown.

- ✅ **Contracts VERIFIED** — Evidence Envelope, trust vocabulary, 4-axis case state,
  mission FSM, structured Φ, validity gate. **22 contract tests passing.**
- ✅ Architecture locked; failure matrix written (47 threats).
- ⚠️ **Go/no-go NOT ESTABLISHED** — existing harness invalid; rebuild is ROLE 01 days 1–3.
- ❌ **Scientific pipeline not implemented** — all modules scaffolded.
- ❌ Stack never started; Docker images never built; OpenDrift not installed.
- ❌ P0 threat coverage: 4 of 27 tested.

---

## Roadmap

**Now (7 days)** — implement the pipeline end to end on CASE-0001 with the gates enforced,
rebuild the go/no-go honestly, publish calibration.

**Next** — real forcing at scale, PRAHARI over a wider region, multi-product ensembles,
richer behavioural priors, aerial-verification feedback into calibration.

**Later** — operational AIS integration where permitted, CAP-compatible dissemination,
native field client, sensor-tasking cues from the latent hypothesis.

---

<p align="center">
  <em>Named for the Vedic god of the ocean and of ṛta — cosmic law — the deity who binds those who break it.</em>
</p>
