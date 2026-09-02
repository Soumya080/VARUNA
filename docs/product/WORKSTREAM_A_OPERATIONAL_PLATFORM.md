# Workstream A — Operational Platform

**Date:** 2026-09-02
**Verified:** real Chromium E2E against the running stack, plus the full backend suite.

The complete chain now runs end to end:

```
VARUNA state/evidence (OperatorCase)
  → Event Spine              (existing EventSpine, extended usage)
  → Material Change Engine   (NEW — varuna_alerts/material_change.py)
  → Alert Generation         (NEW — varuna_alerts/orchestrator.py)
  → Deduplication            (NEW — dedupe_identity, dimension-scoped)
  → Enrichment               (previous/current, severity_basis, evidence refs)
  → Prioritization           (LOW/MEDIUM/HIGH/CRITICAL, explainable)
  → Role-Based Routing       (NEW — varuna_alerts/routing_policy.py)
  → Channel Orchestration    (NEW — varuna_alerts/channel_orchestrator.py)
  → Delivery Tracking        (NotificationDelivery, honest statuses)
  → ACK / Escalation / Resolution  (existing service, extended lifecycle)
  → Mission Authorization    (existing, unchanged, still enforced)
  → PRAMAN Audit             (transition artifacts)
  → SMRITI                   (CaseMemory persistence, advisory only)
  → PDF Incident Report      (NEW — varuna_integration/incident_report.py)
```

## Architectural placement

`GoldenCaseWorkflow` is **not** modified to run any of this. The operational
loop sits at the same composition boundary ADR-0013 established for
intelligence — `varuna_integration/operational_loop.py` runs *after*
`build_product_case()`. A failure in alerting therefore cannot corrupt a
scientific run, and there is no competing canonical workflow.

No Kafka / Flink / Kubernetes / Celery was introduced. The event spine is
the pre-existing deterministic in-process `EventSpine`.

## Material Change Engine

Answers "what changed enough that an operator should care?" by diffing the
current composed `OperatorCase` against the previous snapshot for that case.

| Dimension | Trigger |
|---|---|
| `detection.presence` | first detection produced |
| `detection.confidence` | \|Δ\| ≥ 0.10 |
| `origin.position` | starting point moved ≥ 5 km |
| `attribution.posterior` | first produced, or \|Δ\| ≥ 0.10 |
| `validity.state` | gate state changed |
| `landfall.prediction` | landfall count changed |
| `mission.state` | a mission's state changed |

Thresholds are **operator-attention** thresholds, declared as constants with
a stated rationale — explicitly *not* scientific significance thresholds.
They never alter a value, and an uncalibrated posterior stays uncalibrated.

Deterministic by construction: no clock, no randomness, no model call. Same
`(previous, current)` pair → same result, always.

Every change carries previous value, new value, dimension, reason,
`severity_basis`, and evidence references.

## Severity (Phase 5)

`AlertSeverity` was **extended additively** with LOW/MEDIUM/HIGH; INFO/
WARNING/BLOCKED remain and are still produced by the legacy
`infer_severity()`. CRITICAL was previously documented as unreachable
because no urgency policy existed — one now does, so its docstring was
updated rather than left contradicting reality.

CRITICAL is reachable **only** from state this system actually computes:
a predicted landfall *while the validity gate withdraws operational
authorisation*. No severity is derived from an uncalibrated model score.

## Deduplication (Phase 4) — the implemented rule

```
dedupe_key = case_id | material_dimension | event_type | window
```

Deliberately **not** the alert text (a reword would look new) and **not**
the changed value (every wobble would look new — the engine has already
decided the move was material, so the *dimension* is the right
granularity). `window` is a discrete bucket, not a timestamp, so replay is
deterministic.

## Role routing (Phase 6)

Policy-driven on `(dimension, severity)`, never "notify everyone".

| Dimension | Roles |
|---|---|
| detection.presence | duty_officer |
| origin.position | duty_officer, field_operator |
| attribution.posterior | duty_officer, enforcement |
| validity.state | duty_officer, supervisor |
| landfall.prediction | duty_officer, supervisor, state_pcb, dg_shipping |
| mission.state | duty_officer, field_operator, supervisor |
| *any* CRITICAL | + supervisor |
| no rule matched | duty_officer only (stated in the reason) |

`OperationalRole` is kept distinct from `varuna_infra.rbac.Role`:
notification lists must never grant authority. `ROLE_RBAC_BRIDGE` is the
explicit mapping, and external stakeholders (`enforcement`, `dg_shipping`,
`state_pcb`) map to `None` — they can be told, never act.

## Channel orchestration (Phase 7) — honest integration status

| Channel | Mode | Reality |
|---|---|---|
| `dashboard` | **REAL** | cockpit reads the alert store directly |
| `browser_push` | **SIMULATED** | recorded server-side; real Web Push needs a VAPID keypair + service worker, neither exists here |
| `email` | **NOT_CONFIGURED** (REAL when `VARUNA_SMTP_HOST` + `VARUNA_ALERT_TO` set) | real `smtplib` send when configured |
| `sms` | **NOT_CONFIGURED** | no provider client implemented |
| `whatsapp` | **NOT_CONFIGURED** | adapter shape only |
| `zoho_cliq` | **NOT_CONFIGURED** | optional; **excluded from `DEFAULT_CHANNELS`** so it can never be a critical dependency |

An unconfigured integration reports `NOT_CONFIGURED`, never `SUCCESS`. If no
channel confirms delivery the alert honestly stays `DELIVERY_PENDING`.

## Alert lifecycle (Phase 3)

```
CREATED → ROUTED → DELIVERY_PENDING → DELIVERED → ACKNOWLEDGED → ESCALATED → RESOLVED
```

An operator may act from CREATED/ROUTED/DELIVERY_PENDING/DELIVERED (a human
should not have to wait for outbound orchestration). Invalid transitions are
rejected (`DELIVERED → RESOLVED` is illegal; acknowledge first). Every
transition appends to `AlertRecord.transitions` with actor + reason + time,
and is registered as a PRAMAN artifact when PRAMAN is wired.

`is_simulated` is derived from **engine_mode**, not evidence_mode: a REPLAY
run of a fixture whose evidence is `real` is still not a live operational
event and must never be presented as one.

## Single alert producer

The legacy delivery-receipt correlation (`_sync_alerts_to_lifecycle`) is no
longer wired in `get_golden_case_workflow()`. The Alert Orchestrator is the
single alert producer, writing to the single `InMemoryAlertStore` shared
with `AlertLifecycleService`.

## SMRITI (Phase 11)

`run_operational_loop()` persists a `CaseMemory` per completed case using
SMRITI's existing contract — no new memory schema. Advisory only: it never
overrides evidence, validity, or authorization. `provenance_source` is
`varuna.operational_loop`. Similar-case retrieval is surfaced in the report.

## PDF report (Phase 12)

`GET /v1/cases/{case_id}/report` → real reportlab PDF (~8.8 KB), 15 sections.
Reads the **same composed OperatorCase the cockpit shows**, so report and
screen can never disagree. A case that was never run returns **404** — the
report is never generated from a fabricated case. Unavailable sections are
printed as `NOT_AVAILABLE` / `NOT_CONFIGURED`, never filled in.

## New API surface

| Route | Purpose |
|---|---|
| `GET /v1/cases/{case_id}/operational-summary` | alerts (routing, deliveries, transitions) + missions + channel report |
| `GET /v1/cases/{case_id}/report` | incident PDF |

Existing `POST /v1/alerts/{id}/{acknowledge,escalate,resolve}` and
`POST /v1/missions/{id}/approve` are unchanged and still RBAC-enforced
server-side (401 unauthenticated, 403 unauthorized).


## Tests

| Suite | Result |
|---|---|
| `tests/unit/test_workstream_a_operational.py` (new) | **23 passed** — material change, severity, dedupe, routing, channel honesty, lifecycle |
| `tests/api/test_workstream_a_endpoints.py` (new) | **10 passed** — operational summary, channel report, fail-closed, replay determinism, PDF, SMRITI, RBAC |
| `tests/api/` (all) | **51 passed** |
| Full backend `pytest tests/ --ignore=tests/scientific` | **902 passed, 10 skipped, 1 pre-existing unrelated failure** (`test_netra_training_loop`) |
| Frontend | `tsc --noEmit` 0 errors · `npm run build` 14/14 routes |

An earlier full run showed 3 additional failures in
`tests/integration/test_chhaya_v2_pipeline.py`. That file was created
mid-run by parallel Workstream B work; it passes in isolation and passes
alongside every Workstream A test (78/78 together), and the clean re-run
above is green. Those are not Workstream A regressions.

## Chromium E2E (real browser, running stack)

| Step | Result |
|---|---|
| LOGIN officer | ✔ `OF \| officer \| Duty Officer` |
| RUN VARUNA → material change | ✔ **Alert Center (4)** |
| Channel modes | ✔ dashboard REAL · browser_push SIMULATED · sms/email/whatsapp/zoho NOT_CONFIGURED |
| Severity + dimension | ✔ HIGH detection.presence · MEDIUM attribution.posterior · MEDIUM validity.state · HIGH landfall.prediction |
| Routing | ✔ landfall → duty officer, supervisor, **state pcb, dg shipping**; detection → duty officer only |
| Delivery + transitions | ✔ `- → created → routed → delivery_pending → delivered` with actors |
| ACK | ✔ "Acknowledge confirmed by backend." |
| ESCALATE | ✔ "Escalate confirmed by backend." |
| Mission authorization | ✔ "Mission authorized — confirmed by backend." |
| PRAMAN | ✔ case, run id, artifacts, actor, model versions |
| Report download | ✔ `VARUNA-incident-REPLAY-CASE-VALID.pdf` 8826 bytes, header `%PDF-` |
| Unauthorized (analyst escalate) | ✔ **403** → "NOT AUTHORIZED — analyst lacks this permission." |
| CASE-OOD fail-closed | ✔ no starting point, no geographic evidence, **"No alerts for this case… no alert is fabricated"** |
| Failed network requests | ✔ **NONE** |

The only non-200 `/v1/` responses were the two intentional negative paths
(403 analyst escalate, 400 duplicate mission transition on an already
ASSIGNED mission).

## Remaining gaps (honest)

1. **Escalation is not time-based.** There is no auto-escalation on ACK
   timeout — escalation is operator-initiated only. An SLA timer would need
   a scheduler, which the no-Celery constraint excludes.
2. **Email/SMS are NOT_CONFIGURED in this deployment.** Email will genuinely
   send when `VARUNA_SMTP_HOST` + `VARUNA_ALERT_TO` are set; SMS names a
   provider but no provider client is implemented, so it reports
   NOT_CONFIGURED even when the env vars exist rather than faking a send.
3. **Browser push is SIMULATED**, not real Web Push (no VAPID keypair or
   service worker in this repo).
4. **Alert stores are in-process.** Restarting the API clears alert
   lifecycle state; the snapshot store resets too, so the next run re-emits
   first-sighting material changes.
5. **The material-change window is `"run"`**, a single bucket. A real
   deployment would want a time-bucketed window; that would need a clock
   and would trade away exact replay determinism, so it was not done.
6. **`landfall.predicted` triggers on landfall COUNT changing**, not on the
   predicted location moving — the fixture has one landfall, so a
   position-shift rule could not be verified against real data.
7. **9 legacy frontend pages remain mock** and are untouched; the canonical
   cockpit at `/` is mock-free.
