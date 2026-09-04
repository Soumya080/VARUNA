# VARUNA GRID v2 — running the full system on another device

Every step below was verified by cloning this repository from GitHub into an
empty directory and following it start to finish, on a stock Python that was
NOT the development interpreter. That run is what this document describes —
not what worked on the machine it was written on.

It found four things that could not reproduce on the dev box, all now fixed:
the install was hard-blocked by a Python pin, `pytest` collected zero tests
without an optional extra, one test depended on a 25 MB file that is not in
git, and `requirements.txt` named an extra that does not exist.

No Postgres / Redis / MinIO / Docker is required. The default configuration
uses file-backed JSONL state under `reports/state/`.

---

## 0. Prerequisites

| Need | Verified |
|---|---|
| Python | **3.11.9** in a clean clone, and 3.12.14 on the dev box. 3.11 is the floor. |
| Node.js | **24.x** (`npm install` -> 400 packages, 0 vulnerabilities) |
| Git | any |

> Python 3.11 works. `pyproject.toml` used to pin `>=3.12`, which failed the
> install before a single dependency downloaded — if a teammate hit
> `requires a different Python`, that was this, and it is fixed.

Internet is needed for **map tiles** (Esri / OpenStreetMap). Everything else
runs offline.

---

## 1. Clone

```bash
git clone https://github.com/Soumya080/VARUNA.git
cd VARUNA
git checkout feat/netra-real-training
```

> The working code is on the **`feat/netra-real-training`** branch, not the
> default branch. Check it out before doing anything else.

## 2. Backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
```

Create `.env` in the repo root (it is gitignored — copy from `.env.example`):

```bash
cp .env.example .env
```

The defaults are correct for a local run:

```
USE_POSTGRES=false
USE_MINIO=false
DEMO_MODE=false
```

> `JWT_SECRET_KEY` has a documented insecure development default in
> `apps/api/config.py`. Override it via the environment before any
> deployment that is not on a trusted local machine.

**Start the API** (from the repo root, with the venv active):

```bash
# Windows (PowerShell/bash):
PYTHONPATH=packages python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Check: <http://127.0.0.1:8000/health> → `{"status":"ok",...}`
API docs: <http://127.0.0.1:8000/docs>

## 3. Frontend

```bash
cd frontend/VARUNA-frontend_yash
npm install
npm run dev
```

Open <http://localhost:3000>.

If your API is not on `http://localhost:8000`, create
`frontend/VARUNA-frontend_yash/.env.local`:

```
NEXT_PUBLIC_VARUNA_API_URL=http://127.0.0.1:8000
```

(That file is gitignored. Without it the frontend falls back to
`http://localhost:8000`, which is correct for the standard local setup.)

---

## 4. Log in

Profile widget, **top right** of the header. Demo accounts live in
`packages/varuna_infra/demo_users.py` (a disclosed, dev-only registry — not
a production credential store):

| Username | Password | Role |
|---|---|---|
| `officer` | `officer-demo-pass` | Duty Officer — can ACK/escalate/resolve alerts **and authorize missions** |
| `analyst` | `analyst-demo-pass` | Analyst — can acknowledge only |
| `admin` | `admin-demo-pass` | Administrator |
| `field` | `field-demo-pass` | Field Operator |
| `viewer` | `viewer-demo-pass` | Read Only |

Use **`officer`** for the full demo.

---

## 5. The 90-second demo path

1. Open <http://localhost:3000>, sign in as `officer`.
2. Scenario **CASE-VALID** is selected. Click **RUN VARUNA**.
3. Watch the left timeline light up from real backend SSE events (13 stages).
4. Map opens over the **Gulf of Mexico** (MC20 site, 28.936 N / 88.970 W) —
   satellite basemap, slick footprint, Φ support, starting point, landfall.
5. **Alert Center** shows 4 alerts with severity, the material dimension
   that changed, routing (landfall reaches State PCB + DG Shipping), and
   per-channel delivery status.
6. Click **Acknowledge**, then **Escalate** — each only turns green after
   the backend confirms.
7. **Authorize mission** → mission flips to `ASSIGNED / Authorized by officer`.
8. Click **Download report** → real PDF incident report.
9. Switch to **CASE-OOD** and run it → fail-closed: no starting point, no
   alerts, recommendation `unavailable`. Nothing is fabricated.
10. Log out, log in as `analyst`, try **Escalate** → honest
    **NOT AUTHORIZED** (real 403 from the backend).

---

## 6. Tests

```bash
# fast, no services needed
PYTHONPATH=packages python -m pytest tests/api tests/unit -q

# full backend suite
PYTHONPATH=packages python -m pytest tests/ -q --ignore=tests/scientific
```

Expect **876 passed, 4 skipped** on a base install (verified 2026-09-04,
after the B1/B2/M1-M10 correctness-audit fixes — see
`docs/product/HONESTY_LEDGER.md`). The skips are real and intentional: torch
lives in the optional `ml` extra, so NETRA training tests cannot run without
it, and one test needs a 25 MB NETRA Gold manifest that is not in git. Each
says so by name rather than passing vacuously.

Install the extra to run them too (large — pulls torch):

```bash
pip install -e ".[ml]"
```

With the extra present, the dev box collects 745 tests and 740 pass. The one
failure, `tests/unit/test_netra_training.py::test_netra_training_loop`, is
pre-existing and unrelated (`NetraSample` not subscriptable).

### Real-browser E2E (optional)

```bash
pip install -e ".[dev]"        # NOT ".[e2e]" — that extra does not exist
playwright install chromium
PYTHONPATH=packages python scripts/judge_test.py
PYTHONPATH=packages python scripts/restart_survival_check.py
```

Both servers must be running first. On a small system drive, install the
browser elsewhere:

```bash
PLAYWRIGHT_BROWSERS_PATH=/some/large/disk/pw-browsers playwright install chromium
```

> The `.playwright-browsers/` directory is gitignored (702 MB) — reinstall
> rather than clone it.

---

## 7. What needs data that is NOT in the repo

| Feature | Needs |
|---|---|
| CHHAYA vessel detection producing **candidates** | The MC20 tiles **are** committed (19 MB, `data/gold/events/mc20_v0_1/`) and CHHAYA runs on them — but they are normalised to [0,1] for NETRA segmentation, so CFAR cannot fire. The endpoint says so explicitly rather than reporting an empty ocean. Producing candidates needs raw sigma0 / uncalibrated GRD amplitude tiles, which are not in the repo. |
| xView3 detector | The published checkpoint (220 MB, not committed) **and** a bathymetry raster for the event, which does not exist here. |
| Email alerts | SMTP credentials **and** a real address in `configs/recipients.yaml` (every entry ships as `null`). Missing either → `NOT_CONFIGURED`, never a faked send. See section 9. |
| SMS | Real MSG91 and Fast2SMS clients are implemented. Needs `VARUNA_SMS_PROVIDER` + `VARUNA_SMS_API_KEY` + an E.164 phone number in `recipients.yaml`. |
| WhatsApp / Zoho Cliq | No provider client implemented — always `NOT_CONFIGURED`. |
| Live data ingestion | Adapters exist but the API still uses `AdapterRegistry.create_mock()`. |

---

## 8. Troubleshooting

**Login fails / 404 on `/v1/auth/login`** — a stale API process from a
different Python environment is probably holding port 8000. Check what owns
it and restart from this repo's venv:

```bash
# Windows
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select OwningProcess
```

**Map is blank** — no internet; tiles come from Esri/OSM.

**CHHAYA says "No MC20 tile records"** — you are on a clone made before the data
was committed. `git pull` and confirm
`data/gold/events/mc20_v0_1/sar/tile_records.json` exists. The rest of
`data/gold` (131 GB) is intentionally not in git; only this 19 MB event is.

**PDF download fails** — click **RUN VARUNA** first. The report is generated
from the composed case held in the API process, so a case that has not been run
since the last API restart returns 404 with that explanation. A 503 instead
means `reportlab` is missing: re-run `pip install -e .`.

**Frontend can't reach the API** — check `NEXT_PUBLIC_VARUNA_API_URL`; it is
inlined at dev-server start, so restart `npm run dev` after changing
`.env.local`.


---

## 9. Email and SMS (optional, but this is what "alerting" means)

Out of the box every channel reports `NOT_CONFIGURED`. That is honest, not
broken: nothing is ever reported as delivered when it was not.

**Two** things are needed, and supplying only the first still leaves you at
`NOT_CONFIGURED`.

**1. Credentials** — in `.env` (gitignored):

```
VARUNA_SMTP_HOST=smtp.gmail.com
VARUNA_SMTP_PORT=587
VARUNA_SMTP_USER=you@gmail.com
VARUNA_SMTP_PASSWORD=<16-char Google App Password>
VARUNA_ALERT_FROM=you@gmail.com

VARUNA_SMS_PROVIDER=msg91          # or fast2sms
VARUNA_SMS_API_KEY=...
VARUNA_SMS_SENDER_ID=...
```

Gmail rejects your normal account password over SMTP. Generate an App
Password: Google Account -> Security -> 2-Step Verification -> App passwords.

**2. Recipients** — in `configs/recipients.yaml` (committed, no secrets):

```yaml
recipients:
  duty_officer:
    email: "someone.real@example.com"
    phone: "+919876543210"     # E.164, or MSG91/Fast2SMS reject it
```

**Verify without guessing** — admin-only, sends a real message marked as a
test:

```bash
curl -X POST http://127.0.0.1:8000/v1/alerts/test-notification   -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"   -d '{"role":"duty_officer"}'
```

It returns exactly what each channel reported. `NOT_CONFIGURED` is a
successful call with an honest answer, not an error.

**Verify the email path with no mailbox at all.** Useful before a demo, and
proof the code works independently of anyone's credentials:

```bash
python scripts/smtp_sink.py --port 1025          # terminal 1
# then point VARUNA_SMTP_HOST=127.0.0.1, PORT=1025, VARUNA_SMTP_STARTTLS=0
```

Messages land as `.eml` files in `reports/product/_smtp_capture/`. The sink
delivers nowhere and refuses STARTTLS rather than pretending to upgrade.

---

## 10. Run exactly one API process

The JSONL stores load from disk at startup and never re-read. Two `uvicorn`
processes therefore hold **divergent state**: whichever loses the race for
port 8000 keeps serving its own stale copy, and acknowledgements or mission
approvals appear to vanish at random.

This is the single most confusing failure mode in the system, and it looks
exactly like a persistence bug. Before debugging anything stateful:

```bash
# Windows
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*uvicorn*' } |
  Select-Object ProcessId, CommandLine

# macOS/Linux
ps aux | grep '[u]vicorn'
```

Kill all but one. Single-process is the supported mode; multi-worker
deployment is out of scope.

---

## 11. What a clean clone actually produced

> **Note (2026-09-04):** the table below is the historical record of that
> specific clean-clone run and is left as originally verified. The test
> COUNT in it predates the B1/B2/M1-M10 correctness-audit fixes (see
> `docs/product/HONESTY_LEDGER.md`), which added new regression-lock tests
> and fixed 5 previously-failing ones — the current true count, verified on
> the dev box, is in section 6 above (**876 passed, 4 skipped, 0 failed**).
> This table has not been re-run on an actual clean clone since the audit;
> do that before trusting the other rows (login, CHHAYA tiles, etc.) as
> still current.

Verified on Python 3.11.9, API on :8100, frontend on :3100, no `.env` file
at all:

| Check | Result |
|---|---|
| `pip install -e .` | 90 packages, 0 errors |
| Core module imports (incl. `apps.api.main`) | 10 / 10 |
| `pytest tests/unit tests/api` | **635 passed, 28 skipped, 0 failed** |
| MC20 SAR tiles present and loadable | 9 / 9, `(2, 512, 512) float32` |
| API boots with no `.env` | `{"status":"ok"}` |
| Login -> `POST /v1/auth/login` | 200 |
| `GET /v1/replay/CASE-VALID` | 200 in 0.58 s, validity `valid` |
| Starting point | `STARTING_POINT_AVAILABLE` at -88.970, 28.936 |
| Alerts | 4 |
| CHHAYA tiles | 9 |
| PDF report | 200, 8735 bytes, real `%PDF-` |
| `npm install` | 400 packages, 0 vulnerabilities |
| Cockpit / login / cases / alerts in a real browser | all render real data, 0 failed requests |

The dev box, for comparison: 745 tests collected, 740 passed, 1 pre-existing
NETRA training failure unrelated to any of this.
