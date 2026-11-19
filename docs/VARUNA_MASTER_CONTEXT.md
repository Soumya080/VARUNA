# VARUNA GRID v2 — Master Context (Session Takeover Update)

**Updated:** 2026-09-01T14:30 IST  
**Audit type:** Full project reconstruction from repository  
**Previous context:** `VARUNA_MASTER_CONTEXT.md` (root, 733 lines, design-phase)  
**Previous audit:** `reports/project/VARUNA_FINAL_PROJECT_STATUS.md` (31 Aug 2026)

---

## 1. Project Identity

| Field | Value |
|---|---|
| **Project** | VARUNA GRID v2 |
| **PS** | SIH26143 — Oil spill detection + vessel attribution |
| **Organization** | NTRO |
| **Near-term goal** | Hackathon-grade full working prototype |
| **Later goal** | Research-grade evaluation / benchmarking |
| **Philosophy** | Evidence-aware, fail-closed, provenance-preserving, modular |

---

## 2. Architecture Pipeline (Status as of 2026-09-01)

```
Data Sources ──► Data Guard ──► NETRA ──► PRATIVARTAN ──► NYAYA ──► CHHAYA ──► PRAVAAH ──► Validity ──► ABHIYAN ──► Mission ──► Alerts ──► OperatorCase ──► Dashboard
    ✅            🟢            🟡          🟢              🟢         🔴          🟢           🟢          🟢          🟢         🟢          🟢               🟡
```

---

## 3. Master Component Board

| Component | Status | Evidence | Owner | Next Action | Priority |
|---|---|---|---|---|---|
| Sentinel-1/SAR ingestion | ✅ COMPLETE | Real SAFE calibration validated | Data Eng | — | — |
| AIS ingestion | ✅ COMPLETE | Real MC20 bronze, 11/11 tests | Data Eng | — | — |
| ERA5 | ✅ COMPLETE | Real cube, sufficient status | Data Eng | — | — |
| CMEMS | ✅ COMPLETE | Real cube, sufficient status | Data Eng | — | — |
| NETRA v0.2 baseline | ✅ FROZEN | Hash-verified checkpoint, IoU 0.6458 | ML | — | — |
| NETRA v0.3-B1 | 🟡 PARTIAL | Training DONE, evaluation PENDING | ML | CALM-GRD-HOLDOUT eval | P0 |
| PRATIVARTAN / Φ | ✅ COMPLETE | Real ensemble, real forcing, sensitivity validated | Science | Sensitivity sweep integration (optional) | P4 |
| NYAYA | ✅ COMPLETE | Real Bayesian attribution, 30 tests | Science | — | — |
| Validity Gate | ✅ COMPLETE | 11 checks, 17 tests, fail-closed proven | Science | — | — |
| CHHAYA | 🔴 BLOCKED | Interface + mock only, no real model | ML | Formal disclosure or simple impl | P5 |
| PRAVAAH | 🟢 READY | Real forward drift, pipeline-wired (line 197) | Science | — | — |
| ABHIYAN | 🟢 READY | 5-state gate matrix tested | Ops | — | — |
| Mission FSM | 🟢 READY | Two-step approval enforced | Ops | RBAC-gate approval | P6 |
| Alerts | 🟢 READY | Severity/dedupe/routing real, channels disabled | Ops | — | — |
| Case Engine | 🟢 READY | GoldenCaseWorkflow canonical, reconciled | Integration | — | — |
| OperatorCase | 🟢 READY | 8 sections, 19+27 tests | API | — | — |
| Frontend | 🟡 PARTIAL | Vite/React scaffold, `temp-app` | Frontend (other eng) | Real map/routing | P9 |
| Foundation | 🟡 PARTIAL | Event spine + storage real; observability/RBAC stubs | Platform | RBAC enforcement | P6 |
| Benchmarking | ⚪ DEFERRED | Evaluator infra exists; go/no-go harness invalid | Research | Post-prototype | P10 |

---

## 4. NETRA History

### v0.2 Baseline (FROZEN)
- Checkpoint: `netra_baseline_v02_dac482fcd84a_best.pt`
- Hash: `9f38c690d0ef1629bdc7a59b76dbe054d45245cfccb4ba5b26f242f1d2e2cd66`
- Official test: IoU 0.6458, Dice 0.7848, PR-AUC 0.8513, threshold 0.806
- MC20 result: OOD / no detection (max prob 3.05e-6)
- Root cause: MIXED_CAUSE (domain shift + preprocessing)

### v0.3-B1 Domain Expansion (JUST COMPLETED)
- Training: 30/30 epochs, 59225.8s (≈16.5h), seed 42
- Loss trajectory: 0.9429 → ~0.012 (final window average)
- Architecture: ResNet34 U-Net, 2-channel (VH, VV), 2-class
- Data: 34,992 strong tiles + 213 weak tiles (10% ratio)
- Loss: L_strong + L_weak_negative + L_MIL (1.0/1.0/1.0)
- Checkpoint: `artifacts/experiments/netra_v03/pilot_01_run2/last.pt`
- **NO evaluation exists yet** — this is the critical next step

### Evaluation Protocol (pre-registered)
1. CALM-GRD-HOLDOUT (primary): 215 tiles from 14 held-out ESSD scenes
2. Source-domain preservation: compare v0.3 vs v0.2 on Zenodo Part III
3. MC20 external: evaluate on real MC20 tiles
4. Compare against v0.2 numbers
5. Classify: V03_B1_SUCCESS / PARTIAL_SUCCESS / NO_GENERALIZATION_GAIN / REGRESSION / TRAINING_FAILED

---

## 5. Track 2 Status: COMPLETE AND FROZEN

- PRATIVARTAN: real ERA5/CMEMS-backed advection, real backward ensemble
- NYAYA: real Bayesian attribution, fail-closed
- Validity Gate: 11 checks, fail-closed proven both directions
- AIS: real MC20 bronze data, canonical join
- Φ sensitivity sweep: validated (500p×20ens×7) but not pipeline-wired (optional)
- PhiField: real, provenance-preserving

**DO NOT REOPEN unless genuine regression found.**

---

## 6. Case Engine Status: RECONCILED

- **Canonical path:** `GoldenCaseWorkflow` (567 lines)
- Adapts `CaseWorkflow` persistence + `RealE2EPipeline` producer stages
- Idempotency: `(case_id, config_hash)` cache keying
- Deterministic `run_id`: SHA-256 over case/mode/config/model/dataset
- 6 replay fixtures available
- `CaseWorkflow` still callable (not deleted per convention) — social risk

---

## 7. PRAVAAH Status: INTEGRATED

- `_forecast()` method exists at `pipeline.py:495` and IS called at line 197
- `CubeBackedPravaahProvider`: real forward drift on real current field
- `ForwardForecast` carries `evidence_mode`, `provenance`, `case_id` (ADR-0009)
- `MockPravaahProvider`: unconditionally SIMULATED
- Fail-closed: OOD mid-trajectory freezes, malformed upstream detection handled

---

## 8. Mission / Alerts / ABHIYAN

- ABHIYAN: binary-correct gate (VALID/DEGRADED → dispatch; RESTRICTED/INCONCLUSIVE → zero)
- Mission FSM: two-step approval, `approved_by` exists but RBAC unchecked
- Alerts: severity/dedupe/materiality/role-routing modules real
- Real channels (SMTP/Twilio/CAP-XML) disabled by design

---

## 9. Known Gaps and Risks

1. **NETRA MC20 = real null** — any demo must not fabricate detection
2. **CHHAYA = no real model** — interface + mock heuristic only
3. **RBAC = defined but unused** — `has_permission()` has zero callers
4. **Frontend = scaffold** — `temp-app`, no map/routing
5. **Observability = 13-line stub**
6. **go/no-go harness = scientifically invalid** (self-documented, EvidenceEnvelope construction error)
7. **Φ sensitivity sweep not pipeline-wired** (validated standalone)

---

## 10. Hackathon Demo Path

```
REPLAY case (SIMULATED label) → Detection → Origin → AIS → Validity → Forecast → ABHIYAN → Mission → Alert → OperatorCase → Dashboard
```

Also demonstrate: real MC20 fail-closed path (OOD → safe downstream handling)

---

## 11. Priority Order (Repository-Verified)

1. ⭐ **B1 CALM-GRD-HOLDOUT evaluation** (training just finished)
2. Verify Case Engine ↔ PRAVAAH ↔ Mission ↔ OperatorCase E2E
3. Populated replay case (clickable)
4. Start live backend stack
5. RBAC-gate mission approval
6. Full E2E demo
7. Hackathon demo freeze
8. Benchmarking infrastructure
