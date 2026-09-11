# PharmaFlow AI — Reverse-Chain Compliance Platform

Operationalizes CDSCO's 2025 drug-disposal mandate: **retailer → distributor → manufacturer →
authorized biomedical-waste facility**, with a state drug controller and a shared, tamper-evident
registry across the chain.

> Once a medicine enters the return pipeline, the system creates a verifiable digital chain of
> custody and makes re-entry detectable at the point of sale.

PharmaFlow does **not** take physical custody of medicines — it is a coordination, verification,
audit and fraud-detection layer connecting licensed entities. It is a **hash-chained, Ed25519-signed,
append-only registry** — blockchain-like tamper evidence without blockchain infrastructure. The
re-entry engine is **deterministic and rule-based** by design.

**All data and licenses in this build are synthetic.** A real deployment operates under applicable
CDSCO, licensing, biomedical-waste and state requirements.

---

## What's in the box

| Layer | Tech |
|---|---|
| Frontend (one app, role-gated) | Next.js 15 · React 19 · TypeScript · Tailwind v4 · html5-qrcode |
| API | FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic |
| Database | PostgreSQL (target) · SQLite fallback for zero-setup local runs |
| Registry | SHA-256 hash chain · canonical JSON · Ed25519 signatures (one keypair per license) |
| Route optimization | Google OR-Tools capacitated VRP (labelled nearest-neighbour fallback) |
| Jobs | APScheduler — expiry, SLA, registry verification, Merkle checkpoint (every ~90s in demo mode) |
| Notifications | Provider abstraction, mock by default, per-recipient delivery status |
| Real-time | Server-Sent Events (`GET /stream`) + in-process event bus fired on `after_commit`; every screen updates live, polls only as a fallback |

## Real-time

Every state-changing action (`registry.record_event`, `notifications.notify`, re-entry blocks)
stages an event on the DB session; a single `after_commit` listener fans it out to all connected
SSE clients, so a client never sees an event before its transaction is durable. The browser opens
**one** `EventSource` per session (`lib/realtime.tsx` → `RealtimeProvider`); `useLiveQuery` refetches
the affected data on a relevant event, on tab focus, and — only while the stream is disconnected —
on a short poll. The topbar shows a **Live / Reconnecting** indicator and a notification bell.

Multi-machine: point every client's `NEXT_PUBLIC_API_URL` at one backend + one Postgres and it just
works — Pharmacy A's action shows on the distributor's and regulator's screens within ~1–2 s, no
refresh. (Single backend process today; for multiple workers, bridge `events.publish` to Postgres
`LISTEN/NOTIFY`.)

### Roles
`RETAILER` · `DISTRIBUTOR` · `MANUFACTURER` · `STATE_DRUG_CONTROLLER` · `ADMIN`. Every account is
tied to a license; a `SUSPENDED`/`EXPIRED` license blocks protected actions. RBAC is enforced at
the API layer (`app/core/deps.py`), never the frontend alone.

### Batch state machine (single source of truth)
```
ACTIVE ─(expiry crossed)─▶ RETURN_INITIATED ─▶ PICKUP_SCHEDULED ─┬─(qty ok)──────▶ PICKUP_CONFIRMED
                            [flagged — fraud                     └─(mismatch)─▶ DISPUTED ─(resolved)─▶ PICKUP_CONFIRMED
                             prevention live]
PICKUP_CONFIRMED ─▶ RECEIVED_BY_MANUFACTURER ─(certificate)─▶ DESTROYED_CERTIFIED   [terminal]
```
No state may be skipped. Enforced at the **service layer** (`app/services/batch_state.py`), the
**API layer**, and the **database layer** — triggers in `app/db/guards.py` (SQLite + PostgreSQL).
Batch identity is `(manufacturer_license_id, batch_number)` — never the batch number alone.
Overlay flags: `NON_COMPLIANT`, `REENTRY_FLAGGED`.

---

## Run it locally (from a clean checkout)

Prereqs: **Python 3.11+** (tested on 3.14) and **Node 20+**.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate       macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:
- **PostgreSQL (recommended):** `DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/pharmaflow`
- **Zero-setup:** leave `DATABASE_URL` blank → a local SQLite file is used.

Create the schema + guards + seed data:

```bash
python -m alembic upgrade head      # schema + DB-level state-machine guards
python -m scripts.init_db           # (also runs the above) + seeds demo batches A–G
```

Start the API:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

OpenAPI docs: <http://localhost:8000/docs> · health: <http://localhost:8000/health>

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000

# For a demo — fast route loads, no per-page compile:
npm run build && npm start

# Or for development:
npm run dev
```

Open <http://localhost:3000>.

> **Windows note:** the npm scripts call `node node_modules/next/dist/bin/next` directly so the npm
> shim doesn't break on repo paths that contain `&` or spaces.
>
> **Demo tip:** use `npm run build && npm start`, not `npm run dev`. Dev mode compiles each route on
> first visit (2–4 s of lag the first time you open a page); the production server serves them
> instantly. Never run `npm run build` while `npm run dev` is running — it corrupts `.next`.

### 3. Tests

```bash
cd backend
python -m pytest -q          # 26/26 — 15 non-negotiable critical tests (Build Spec §13.2) + 11 extended
```

---

## Deploying

**Backend → Render, Frontend → Vercel.** Database stays on Supabase (already provisioned).

Render was chosen over Vercel for the backend because the real-time system (SSE stream +
in-process event bus) and the APScheduler background jobs both live in one process's memory —
they need a persistent long-running server, which serverless functions can't provide.

> **Hard constraint:** the backend must run as exactly **one instance, one worker**. Scaling to
> more requires bridging `app/services/events.py` to Postgres `LISTEN/NOTIFY` or Redis first —
> not built. `render.yaml` already pins `numInstances: 1` and `--workers 1`.

### 1. Backend on Render

1. Render dashboard → **New → Blueprint** → connect the `PharmaFlow-AI` GitHub repo. Render reads
   [`render.yaml`](render.yaml) from the repo root and proposes the `pharmaflow-api` web service.
2. Before the first deploy, fill in the two secrets it left blank:
   - `DATABASE_URL` — your Supabase Postgres connection string (same one in `backend/.env` locally).
   - `CORS_ORIGINS` — leave as `http://localhost:3000` for now; you'll update it once the frontend
     has a Vercel URL (step 3 below).
   - `JWT_SECRET` is auto-generated by Render (`generateValue: true`) — don't reuse the local dev default.
3. Deploy. Once live, note the URL, e.g. `https://pharmaflow-api.onrender.com`, and confirm
   `https://pharmaflow-api.onrender.com/health` returns `{"status":"ok",...}`.
4. Free-tier Render web services sleep after 15 minutes idle (cold start ~30-50s on the next
   request). Fine for async testing; switch the plan to **Starter** before a live/judged demo.

### 2. Frontend on Vercel

1. Vercel dashboard → **Add New → Project** → import the same GitHub repo.
2. In **Project Settings → General → Root Directory**, set it to `frontend` (this is a monorepo —
   Vercel otherwise looks for `package.json` at the repo root and fails). Framework preset
   auto-detects as Next.js; no `vercel.json` needed.
3. **Project Settings → Environment Variables** → add `NEXT_PUBLIC_API_URL` =
   `https://pharmaflow-api.onrender.com` (your Render URL from step 1.3, no trailing slash).
4. Deploy. Note the resulting URL, e.g. `https://pharmaflow-ai.vercel.app`.

### 3. Close the loop: CORS

Back on Render → `pharmaflow-api` → **Environment** → set `CORS_ORIGINS` to your Vercel URL
(`https://pharmaflow-ai.vercel.app`, comma-separate if you also want to keep `localhost:3000` for
local testing) → save, which triggers a redeploy. Without this the browser blocks every API call
with a CORS error even though the backend itself is healthy.

### Shipping changes after deploy

Both platforms auto-redeploy on every `git push` to `main` — no extra step. Commit and push as
usual; Render rebuilds the backend, Vercel rebuilds the frontend, each from the same push. The
only time you touch a dashboard again is when a change introduces a **new** environment variable —
add it there once, since it isn't read from the repo.

---

## Demo accounts (password `demo1234` for all)

| Role | Email |
|---|---|
| Retailer A — CityCare Pharmacy | `retailer.a@pharmaflow.demo` |
| Retailer B — MedPlus Demo | `retailer.b@pharmaflow.demo` |
| Retailer C — Apollo Demo | `retailer.c@pharmaflow.demo` |
| Distributor — Meridian Distribution | `distributor@pharmaflow.demo` |
| Manufacturer — Nucleus Pharma | `manufacturer@pharmaflow.demo` |
| State Drug Controller — Maharashtra | `regulator@pharmaflow.demo` |
| Platform Admin | `admin@pharmaflow.demo` |

The login screen has one-click buttons for each (still real authentication).

### Seeded batches (drug category: antimicrobial — Azithromycin, CDSCO Schedule H2 QR mandate)

| Batch | State | Purpose |
|---|---|---|
| AZ-2025-A | ACTIVE | Healthy. Also exists under a **second manufacturer** (composite-identity demo). |
| AZ-2025-B | ACTIVE | Sitting exactly at the 60-day pre-expiry alert threshold. |
| AZ-2025-C | RETURN_INITIATED | Expired, auto-entered the return pipeline; has a legitimate pre-flag sale. |
| AZ-2025-D | ACTIVE (expired) | Staged for the **fraud demo** — Retailer A initiates its return live. |
| AZ-2025-E | PICKUP_SCHEDULED | Staged for the **quantity-mismatch dispute** demo. |
| AZ-2025-F | RECEIVED_BY_MANUFACTURER | Awaiting a destruction certificate. |
| AZ-2025-G | DESTROYED_CERTIFIED | Full trail, terminal. |

---

## The two demo scripts

Both run for real against the database. **Admin → Demo Control** has a "How to run the demo" guide,
one-click scenario buttons, and a **Simulate activity / Keep simulating** toggle that generates a
small burst of real network activity every 8 s so the Control Tower visibly moves while you present.
`Reset demo data` restores the exact seeded state so the fraud scenario is re-runnable.

Best setup: open **State Drug Controller → Control Tower** on one screen, drive from **Demo Control**
on another — every scenario and every simulated action updates the Control Tower live.

### Fraud scenario (~0.02 s server-side; well under 60 s through the UI)
1. Log in as **Retailer A**, open **Batch D**, **Initiate return** → batch flips to
   `RETURN_INITIATED` and is flagged in the registry (`flagged_at` set).
2. Log in as **Retailer B**, scan the same batch (paste its QR or use *demo scan*).
3. Sale is **blocked at the point of sale**. A re-entry alert panel appears — batch, state,
   attempted location, both notified parties, latency in ms.
4. Log in as the **State Drug Controller** → the alert is on the Control Tower immediately.
5. Open the alert → the complete registry timeline for that batch.

### Happy path
Retailer sale (stock decrements) → expiry crossing auto-creates the return → distributor optimizes
a multi-stop pickup route (OR-Tools) → pickup confirmed, quantity matches → manufacturer receipt →
destruction certificate → `DESTROYED_CERTIFIED` → regulator timeline shows the full retailer →
distributor → manufacturer → certificate trail, registry chain valid.

---

## Registry verification

`GET /registry/verify/{batch_number}` (optionally `?manufacturer_license_id=…`) re-walks a batch's
chain and checks: genesis `prev_hash`, every subsequent `prev_hash`, recomputed SHA-256 hashes,
Ed25519 signatures against the signer's registered public key, and chronological ordering.

Verified in tests: a **directly tampered `registry_events` row** (modified `payload` or `signature`
via raw SQL) is reported as `valid: false` with the specific broken `seq` and reason. The
**Registry Explorer** UI runs the same check with a "Verify chain" action.

A periodic job computes a **Merkle root** over new events and stores it as a checkpoint
(`/registry/checkpoints`) — tamper evidence, not a distributed ledger.

---

## Re-entry detection

Every POS scan synchronously calls `app/services/reentry.py`:
- Indexed lookup on the batch; **time-bound** — only a scan strictly after `flagged_at` is
  suspicious, so legitimate pre-flag sales are never retroactively flagged (tested).
- On a hit: sale blocked, `pos_transactions.flagged/blocked` set, `reentry_alerts` row created,
  batch `REENTRY_FLAGGED`, notifications to the **state drug controller** and the **batch's
  manufacturer**, a `REENTRY_BLOCKED` registry event.
- Measured scan-to-both-notifications latency in this build: **~4–6 ms** (target < 5 s).

---

## Route optimization

`app/services/route_optimizer.py` — Google OR-Tools capacitated VRP. Cost = distance weighted so
stops near an SLA breach are pulled earlier (not a plain distance sort). Constraints: vehicle
capacity, route duration. Output (ordered stops, distance, duration, cost, capacity, urgency) is
persisted to `pickup_routes` and shown on the Distributor screen. If OR-Tools is unavailable it
degrades to a **clearly labelled** nearest-neighbour heuristic (`ortools_used: false`).

---

## API surface (see `/docs` for the full generated spec)

`POST /auth/login` · `GET /retailer/batches` · `POST /retailer/pos/sale` ·
`POST /retailer/batches/{id}/initiate-return` · `POST /retailer/returns/{id}/confirm` ·
`GET /distributor/returns/pending` · `POST /distributor/routes/optimize` ·
`POST /distributor/pickups/{id}/confirm` · `POST /disputes/{id}/evidence` ·
`POST /disputes/{id}/resolve` · `GET /manufacturer/receipts` · `POST /manufacturer/receipts` ·
`POST /manufacturer/certificates` · `GET /registry/batches/{batch_number}/history` ·
`GET /registry/verify/{batch_number}` · `GET /alerts/reentry` · `POST /alerts/reentry/{id}/resolve` ·
`GET /dashboard/summary` · `GET /dashboard/events/stream` (poll fallback) ·
`GET /stream` (Server-Sent Events, primary real-time feed) · `GET /notifications` ·
`POST /notifications/{id}/read` · `POST /notifications/read-all` ·
`GET /dashboard/compliance-export.csv` · `POST /demo/reset` ·
`POST /demo/scripts/{fraud|happy|dispute|pulse}`

---

## Known MVP limitations

- **Default DB is SQLite** unless `DATABASE_URL` points at Postgres. The state-machine guards and
  certificate gate are installed for both dialects; row-level locking is a no-op on SQLite so the
  concurrent-sale guard uses an atomic conditional `UPDATE` (portable, tested) — the same pattern
  now also backs the retailer's return-quantity deduction (see Real-time section above).
- Real-time runs on a single in-process event bus (SSE) — correct for one backend worker. Scaling
  to multiple workers needs a shared bus (Postgres `LISTEN/NOTIFY` or Redis) — not built yet.
- Notifications are mock providers (delivery status shows `simulated` for email/SMS).
- Maps are schematic (ordered stop list), no Mapbox tiles.
- File uploads are represented as `mock://` URLs; the storage layer is abstracted but local.
- Offline distributor queue (IndexedDB) not implemented.
- Return-condition / pickup-weight / dispute-evidence photo capture is metadata-only in the UI.

## Roadmap

Postgres `LISTEN/NOTIFY` (or Redis) bridge so real-time works across multiple backend workers ·
S3-compatible upload storage · offline pickup queue with idempotent sync ·
expiry-risk ML forecasting (optional intelligence, never the fraud mechanism) · Mapbox routing ·
Docker Compose one-command startup · pharmacy-billing-software integration · inter-pharmacy
stock-redistribution for near-expiry batches · Users & Licenses admin console.

## Repo layout

```
backend/app/{core,db,models,schemas,services,api,jobs}   FastAPI application
backend/app/services/events.py                           real-time pub/sub (SSE event bus)
backend/scripts/init_db.py                               schema + guards + seed
backend/tests/test_critical.py                           the 15 non-negotiable tests
backend/tests/test_extended.py                           11 further checks (RBAC, SLA, inventory, audit trail)
frontend/lib/realtime.tsx                                SSE client, useLiveQuery, notifications
frontend/app/(app)/{retailer,distributor,manufacturer,dashboard,registry,alerts,disputes,batch,admin}
PROGRESS.md                                              build/checkpoint log
```
