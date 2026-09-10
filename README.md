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
| Jobs | APScheduler — expiry, SLA, registry verification, Merkle checkpoint |
| Notifications | Provider abstraction, mock by default, per-recipient delivery status |

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
npm run dev
```

Open <http://localhost:3000>.

> **Windows note:** if the repo path contains `&` or spaces, `npm run dev` is already wired to call
> `node node_modules/next/dist/bin/next` directly to avoid the npm shim breaking on those paths.

### 3. Tests

```bash
cd backend
python -m pytest -q          # 15/15 critical tests (Build Spec §13.2)
```

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

Both run for real against the database. **Admin → Demo Control** has one-click buttons; each reports
elapsed time. `RESET DEMO DATA` restores the exact seeded state so the fraud scenario is re-runnable.

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
`GET /dashboard/summary` · `GET /dashboard/events/stream` (short-poll) ·
`GET /dashboard/compliance-export.csv` · `POST /demo/reset` · `POST /demo/scripts/{fraud|happy|dispute}`

---

## Known MVP limitations

- **Default DB is SQLite** unless `DATABASE_URL` points at Postgres. The state-machine guards and
  certificate gate are installed for both dialects; row-level locking is a no-op on SQLite so the
  concurrent-sale guard uses an atomic conditional `UPDATE` (portable, tested).
- Real-time dashboard is a 3.5 s poll, not a WebSocket.
- Notifications are mock providers (delivery status shows `simulated` for email/SMS).
- Maps are schematic (ordered stop list), no Mapbox tiles.
- File uploads are represented as `mock://` URLs; the storage layer is abstracted but local.
- Offline distributor queue (IndexedDB) not implemented.
- Return-condition / pickup-weight / dispute-evidence photo capture is metadata-only in the UI.

## Roadmap

WebSocket streaming · S3-compatible upload storage · offline pickup queue with idempotent sync ·
expiry-risk ML forecasting (optional intelligence, never the fraud mechanism) · Mapbox routing ·
Docker Compose one-command startup · pharmacy-billing-software integration.

## Repo layout

```
backend/app/{core,db,models,schemas,services,api,jobs}   FastAPI application
backend/scripts/init_db.py                               schema + guards + seed
backend/tests/test_critical.py                           the 15 non-negotiable tests
frontend/app/(app)/{retailer,distributor,manufacturer,dashboard,registry,alerts,disputes,batch,admin}
PROGRESS.md                                              build/checkpoint log
```
