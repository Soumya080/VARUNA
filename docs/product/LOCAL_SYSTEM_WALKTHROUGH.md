# VARUNA GRID v2 — Local System Walkthrough

**Frontend:** http://localhost:3000
**Backend:** http://127.0.0.1:8000
**API docs:** http://127.0.0.1:8000/docs

## Demo access

Sign in via the profile widget, top-right of the header (currently shows
"Not signed in"). Demo accounts (`packages/varuna_infra/demo_users.py`,
disclosed there in full — not a secret boundary):

| Username | Role |
|---|---|
| `officer` | Duty Officer (acknowledge/escalate/resolve alerts, approve missions) |
| `analyst` | Analyst (acknowledge alerts only) |
| `admin` | Administrator (all permissions) |
| `field` | Field Operator |
| `viewer` | Read Only |

Passwords follow the pattern `<username>-demo-pass` — see the registry file
directly rather than a password reproduced here.

## Walkthrough

1. **Open** http://localhost:3000 — the dashboard loads with `CASE-VALID`
   as the default replay case (header shows the ENGINE MODE badge:
   `Replay`).
2. **Login** — click the profile widget top-right, enter `officer` /
   its demo password, Sign In. The widget now shows the real username and
   role (Duty Officer).
3. **Open CASE-VALID** — already loaded on the dashboard; the case
   intelligence sidebar and pipeline all read from `GET /v1/replay/CASE-VALID`.
4. **Inspect Detection & Starting Point** — the summary strip shows
   **STARTING POINT 28.936° N 88.970° W · detection centroid**, resolved by
   the backend's explicit Starting Point Contract
   (`OperatorCase.starting_point`) from the validated slick centroid. The
   pipeline view shows the NETRA detection stage (`PRODUCED`,
   `evidence_mode: real`).

   **Note on the map:** CASE-VALID is the MC20 site in the *Gulf of Mexico*,
   but the shipped basemap is a static image of the Arabian Sea. The map
   therefore shows **"BASEMAP DOES NOT COVER THIS CASE"** and hides its
   illustrative overlays rather than drawing the slick at the wrong
   geographic location. That is correct, intended behaviour — not a
   rendering failure.
5. **Inspect Evidence** — the Evidence Health panel in the case-intelligence
   sidebar; components with a real score vs. honestly `—` (unmeasured).
6. **Inspect CHHAYA** — the "Chhaya" panel in the sidebar: source
   hypotheses, methodology, evidence considered.
7. **Inspect NYAYA** — the attribution section on the main pipeline view:
   posterior, top candidate, uncertainty.
8. **Inspect SMRITI** — the SMRITI panel, labelled "Advisory memory — not
   current evidence" (memory hits only, never treated as new evidence).
9. **Inspect Uncertainty** — the Uncertainty panel: OOD assessment and the
   6 independent uncertainty components, never collapsed into one number.
10. **Inspect Next Action** — the Decision Trace panel: the agentic loop's
    recorded reasoning trace and next-best-action recommendation.
11. **Inspect Forecast** — the Forecast panel: PRAVAAH horizon, landfall
    predictions, trajectory file reference, `EvidenceModeBadge`.
12. **Inspect Validity** — the Recommended Action panel's badge and the
    validity gate's state/reasons feeding it.
13. **Inspect Recommendation** — same panel: `VALID` for CASE-VALID. The
    summary strip's **VALIDITY GATE** card reads
    "VALID / allows operational action".
14. **Inspect Alerts** — navigate to **Alerts** in the top nav
    (http://localhost:3000/alerts). One real alert appears for
    `REPLAY-CASE-VALID` (event `validity.evaluated`, severity `WARNING`).
    As `officer`, click **Acknowledge**, then **Escalate**, then
    **Resolve** — each button only enables for its legal next transition,
    and each click shows "confirmed by backend" only after the real
    response returns.
15. **Inspect Mission** — navigate to **Missions**
    (http://localhost:3000/missions). The case's real `OperatorCase.mission`
    is shown (state `AVAILABLE`, not yet approved) alongside the separate
    live `MissionService` list (likely empty — see known gaps below).
16. **Inspect PRAMAN** — the PRAMAN panel in the sidebar: artifact IDs,
    model versions, evidence lineage (each item tagged with its own
    EvidenceMode).
17. **Test authorization** — log out, log back in as `analyst`. Return to
    **Alerts**: acknowledging is allowed, but attempting to escalate or
    resolve returns **"NOT AUTHORIZED"** — the button click genuinely hits
    the backend and reports the real 403, never a fake success.
18. **Logout** — profile widget → Log Out. All authenticated actions now
    show **"Sign in (top right) to act on this alert"** / **NOT
    AUTHENTICATED** instead of silently failing.

## What to look for that proves this is real, not a mock

- The header's ENGINE MODE badge says **Replay**, and every section's own
  EvidenceMode badge is independent of it (a REPLAY case can still carry
  `evidence_mode: real` — the two vocabularies never collapse into one).
- The AIS section on CASE-VALID legitimately reads **not produced** (zero
  tracks in this fixture) — this is correct, not a bug.
- Refreshing the page re-fetches from the backend; alert/session state
  persists across reloads because it lives server-side (alerts) or in
  `localStorage` (your login token), not react-only memory.
- Opening `CASE-OOD` via `GET http://127.0.0.1:8000/v1/replay/CASE-OOD`
  directly shows validity/decision/mission all correctly `not_yet_produced`
  and zero alerts — the fail-closed path.

## Known, disclosed limitations of this local build

- No route creates a **live** mission via the API — the Mission Control
  page's "Live Missions" panel will show empty until one exists;
  mission-approval is fully real and tested, just not reachable from a
  fresh browser session without a pre-existing live mission.
- Demo login is a local/dev-only registry (sha256+salt), not a production
  credential store.
- `landfall.predicted` is a recognized but not-yet-wired alert event type.
