# VARUNA GRID v2 — running the full system on another device

Everything below was verified on the machine this was developed on. No
Postgres / Redis / MinIO / Docker is required for the operator cockpit —
the default configuration uses in-memory repositories.

---

## 0. Prerequisites

| Need | Version used here |
|---|---|
| Python | 3.12 (3.11+ should work) |
| Node.js | 24.x LTS (18+ should work) |
| Git | any |

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

Known: `tests/unit/test_netra_training.py::test_netra_training_loop` fails
pre-existing and unrelated (`NetraSample` not subscriptable).

### Real-browser E2E (optional)

```bash
pip install playwright
playwright install chromium
PYTHONPATH=packages python scripts/judge_test.py
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
| CHHAYA vessel detection producing candidates | Raw sigma0 / uncalibrated Sentinel-1 GRD amplitude tiles. The committed MC20 tiles are normalised to [0,1] for NETRA segmentation, so CFAR cannot fire on them — the endpoint says so explicitly rather than reporting an empty ocean. |
| xView3 detector | The published checkpoint (220 MB, not committed) **and** a bathymetry raster for the event, which does not exist here. |
| Email alerts | `VARUNA_SMTP_HOST` + `VARUNA_ALERT_TO`. Unset → `NOT_CONFIGURED`, never a faked send. |
| SMS / WhatsApp / Zoho | No provider client implemented — always `NOT_CONFIGURED`. |
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

**Frontend can't reach the API** — check `NEXT_PUBLIC_VARUNA_API_URL`; it is
inlined at dev-server start, so restart `npm run dev` after changing
`.env.local`.
