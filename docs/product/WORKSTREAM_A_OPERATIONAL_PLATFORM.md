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


---

# Phase 1–2 follow-up (2026-09-03)

The audits that followed the first Workstream A pass found the engine was
real but crippled in five specific ways. All five are now fixed.

## Persistence — decisions survive a restart

`packages/varuna_infra/jsonl_store.py` generalises the pattern SMRITI already
proved. `KeyedJsonlStore` (last-write-wins) backs alerts and missions;
`AppendJsonlStore` (append-only, order preserved) backs the audit trails,
because an audit log must never be rewritten wholesale — a crash mid-rewrite
could lose earlier decisions.

Persisted under `reports/state/` (gitignored, `VARUNA_STATE_DIR` overrides):

| File | Contents |
|---|---|
| `alerts.jsonl` | lifecycle, transitions, routing, deliveries |
| `missions.jsonl` | incl. `human_approved_by`, `assigned_at`, `state_history` |
| `mission_audit.jsonl` | authorization decisions, allow **and** deny |
| `alert_audit.jsonl` | previously unreadable even at runtime |
| `case_snapshots.jsonl` | material-change baseline |

A corrupt line is skipped and **counted** (`load_errors`) — losing one
malformed record must not cost every acknowledgement ever made.

**Verified by hard process kill:** an acknowledged alert kept its actor, the
mission stayed `assigned` with `human_approved_by`, and the audit entry
survived — with no case re-run.

## Dedupe was lifetime suppression, not a window

`dedupe_identity()` defaulted to the literal string `"run"` and every caller
used the default. Once a dimension had alerted for a case it could never
alert again for the process lifetime — a genuine second landfall hours later
was swallowed and the stale record returned.

Now `dedupe_bucket(clock(), window_seconds)`, default **300 s**, matching the
interval the pre-existing `DedupeWindow` already used so the system has one
suppression interval rather than two. The clock is injectable, so tests pin
time and replay stays deterministic.

## One alert producer, not two

`MissionService` raised `mission.assigned` through the legacy
`AlertService.route_and_send` + `sync_from_deliveries` path, writing
`case:event` keys into the **same store** the orchestrator keys as
`case|dimension|event|window`. Those legacy records had no severity basis, no
routing and no material dimension. `mission.assigned` now goes through the
orchestrator. All five CASE-VALID alerts now carry a dimension and a basis.

## A protection that did not exist

The orchestrator computed a `gate_state` from `check_materiality` and never
used it, while its comment claimed a restrictive validity gate withheld
outbound alerting. Deleted, with a note recording where materiality is
*actually* enforced: upstream in `evaluate_material_changes()`, which emits
nothing for a case whose gate blocks action (CASE-OOD produces zero changes).

## Things that existed but were invisible

- **`GET /v1/alerts`** — new, with `?status=&severity=&case_id=&since=&limit=&offset=`.
  Previously the only way to see an alert was to already know its `case_id`
  or `alert_id`. `GET /v1/alerts/log` is kept so callers do not 404 but now
  declares itself deprecated and structurally always empty
  (`get_alert_service()` is not a singleton).
- **The Event Spine** — `GoldenCaseWorkflow` wrote to a separate
  `_golden_event_store` that no route read, so every `case.stage.*` and every
  material-change event was written somewhere invisible. Both now share the
  store `GET /v1/events` reads: **16 events** for CASE-VALID, including all
  four material changes with severity and dimension.
- **PRAMAN + AuditLog on the orchestrator** — both were supported and neither
  was ever passed, so alert transitions never reached the audit trail.
- **`evidence_refs`** — origin, attribution and validity produced `[]`, the
  three dimensions an operator most wants to drill into. Now populated from
  `envelope.artifact_id` plus parent lineage, e.g. validity carries
  `['gate-REPLAY-CASE-VALID', 'attribution-REPLAY-CASE-VALID']`.
- **`AlertRecord.mission_id`** — a typed alert to mission link; the id
  previously existed only inside prose.

## RUN VARUNA produced no alerts at all

The operational chain ran only from `GET /v1/replay/{fixture}`.
`run_stream.py` composed the case and stopped, so pressing the cockpit's
button executed the science and the alert engine looked dead. It now runs the
loop and reports the genuine outcome in the `ALERT` stage event
(`n_alerts`, `n_material_changes`, `alert_ids`) and in `run_complete`. A
failure surfaces as an error event rather than being swallowed — a silent
alerting failure is indistinguishable from "nothing was material".

## Windows atomic-write race

`os.replace` raises `PermissionError` (WinError 5) when an antivirus or the
search indexer briefly holds the destination. Bounded retry with backoff,
then a loud `OSError` — never a silent lost write. Found as a flaky test;
it was a real data-loss risk.

## Still open in Phase 2

Nothing. Remaining work is Phase 3 (real email/SMS), Phase 4 (mission FSM),
Phase 5 (the frontend mock pages).
