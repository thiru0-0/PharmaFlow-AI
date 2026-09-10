# PharmaFlow AI — End-to-End Build Specification

Reverse-chain compliance platform for CDSCO's drug disposal mandate (PS3). This document defines every feature and the exact working logic behind it, so it can be built directly from this spec.

---

## 1. Feature checklist

**Retailer**
- Expiry monitoring per batch, per pharmacy
- 60-day pre-expiry alert
- Auto-generated return request on expiry crossing
- Return logging: batch photo, condition, quantity
- POS scan-to-sell with automatic stock decrement
- Sale blocking on any batch flagged in the return pipeline
- Retailer compliance status view (own SLA standing)

**Distributor**
- Pending-returns queue, grouped by area
- Optimized multi-stop pickup routing across pending returns
- Pickup confirmation: batch scan, weight-verified photo
- Automatic dispute flagging on quantity mismatch
- Dispute evidence submission
- SLA countdown per batch

**Manufacturer**
- Confirmed-receipts queue
- Biomedical waste facility scheduling
- Destruction certificate upload, gated on confirmed receipt
- Certificate-to-batch linkage (no unlinked certificates)
- Auto-generated disposal record (drug name, batch, expiry, reason)

**Shared registry / ledger**
- Append-only, hash-chained event log
- Per-actor digital signatures on every event
- Periodic network-wide integrity checkpoint
- Full per-batch history query
- Integrity verification job

**Re-entry detection**
- Real-time check of every POS sale scan against flagged batches
- Sale blocking at point of scan
- Immediate alert to state drug controller + manufacturer

**Dispute resolution**
- Evidence submission by both sides
- Adjudication and reconciliation
- Registry update with final resolved quantity

**Compliance tracking**
- Retailer return-window SLA breach detection
- Manufacturer disposal-window SLA breach detection
- Auto-escalation to regulator dashboard on breach

**Notifications**
- Multi-channel (SMS / email / in-dashboard) alerts for: expiry, dispute, non-compliance, re-entry fraud

**Tracking dashboard**
- Network-wide control tower (see Section 7)

**Auth & access**
- License-linked accounts per role
- Role-based access control
- Keypair issuance per license for event signing

---

## 2. System architecture overview

```
Retailer app ──┐
Distributor portal ──┼──▶ API layer (FastAPI) ──▶ PostgreSQL (core data)
Manufacturer portal ──┘         │                  │
                                 │                  └──▶ Registry service (hash-chained log)
                                 ├──▶ Route optimizer (OR-Tools)
                                 ├──▶ Re-entry detection service
                                 ├──▶ Notification service
                                 └──▶ Dashboard read API ──▶ Tracking dashboard
```

All four human-facing surfaces (retailer, distributor, manufacturer, dashboard) are role-gated views of one application — not separate codebases — sharing the same API layer and data model.

---

## 3. Actors & permissions

| Actor | Can do | Cannot do |
|---|---|---|
| Retailer | Log sales, initiate/view own returns, view own compliance status | View other retailers' data, confirm pickups, issue certificates |
| Distributor | View/confirm pickups for mapped retailers, raise/resolve disputes on their pickups | Issue certificates, view unrelated retailers |
| Manufacturer | View confirmed receipts, upload certificates for their own batches | Confirm pickups, act on another manufacturer's batch |
| State drug controller | Read-only access to all registry data, alerts, dashboard | Modify any transactional record |
| Admin (platform) | Full dashboard access, dispute adjudication, user/license management | — |

Every account is tied to a license number; permissions are derived from license type, not just a role flag, so a suspended license can be reflected immediately.

---

## 4. Data model

| Table | Key fields | Purpose |
|---|---|---|
| `users` | id, name, role, license_id, public_key, mapped_distributor_id, mapped_manufacturer_id, location | Account + role + signing key |
| `licenses` | id, license_number, entity_type, state, status, valid_until | Regulatory identity backing each account |
| `batches` | id, drug_name, batch_number, manufacturer_license_id, mfg_date, expiry_date, category, qr_payload | One row per manufactured batch |
| `batch_holdings` | id, batch_id, retailer_id, quantity_on_hand, expiry_alert_sent, last_updated | Per-retailer stock level for a batch |
| `pos_transactions` | id, batch_id, retailer_id, quantity, scanned_at, flagged | Every sale scan event |
| `return_requests` | id, batch_id, retailer_id, distributor_id, quantity_reported, photo_url, status, created_at | A retailer's return, from initiation onward |
| `pickups` | id, return_request_id, distributor_id, route_id, quantity_confirmed, photo_url, status | Distributor-side confirmation of a return |
| `disputes` | id, pickup_id, reported_qty, confirmed_qty, status, resolution_notes, resolved_by | Quantity-mismatch cases |
| `manufacturer_receipts` | id, batch_id, distributor_id, manufacturer_id, received_at, quantity | Confirmed handoff to manufacturer |
| `destruction_certificates` | id, batch_id, manufacturer_id, facility_id, cert_url, issued_at | Final destruction proof |
| `registry_events` | id, event_type, actor_id, batch_id, payload, prev_hash, hash, signature, created_at | The hash-chained audit log |
| `reentry_alerts` | id, batch_id, retailer_id, triggered_at, notified_controller, notified_manufacturer, status | Fraud detections |
| `pickup_routes` | id, distributor_id, route_date, stops, total_distance, total_cost | Optimizer output |
| `notifications` | id, recipient_id, type, payload, channel, sent_at | Outbound alert log |

---

## 5. Batch lifecycle (state machine)

```
ACTIVE ──(60 days to expiry)──▶ ACTIVE [alert sent]
ACTIVE ──(expiry date crossed)──▶ RETURN_INITIATED
RETURN_INITIATED ──(pickup scheduled)──▶ PICKUP_SCHEDULED
PICKUP_SCHEDULED ──(qty mismatch)──▶ DISPUTED
DISPUTED ──(resolved)──▶ PICKUP_CONFIRMED
PICKUP_SCHEDULED ──(qty matches)──▶ PICKUP_CONFIRMED
PICKUP_CONFIRMED ──(manufacturer receives)──▶ RECEIVED_BY_MANUFACTURER
RECEIVED_BY_MANUFACTURER ──(certificate uploaded)──▶ DESTROYED_CERTIFIED  [terminal]
```

Overlay flags, independent of the main state: `NON_COMPLIANT` (SLA window breached while still upstream of `PICKUP_CONFIRMED`), `REENTRY_FLAGGED` (a sale attempt was blocked after `RETURN_INITIATED`).

A batch can only reach `DESTROYED_CERTIFIED` by passing through every prior state in order — there is no path that skips `PICKUP_CONFIRMED` and goes straight to a certificate. This is the hard gate the PS explicitly requires.

---

## 6. Core working logic

### 6.1 Expiry monitoring & auto-return trigger
- A daily job scans `batch_holdings` where `quantity_on_hand > 0`.
- If `expiry_date - today == 60` and `expiry_alert_sent = false`: notify the retailer, set the flag (idempotent — never re-sent).
- If `today >= expiry_date` and no open `return_requests` exists for that batch+retailer: auto-create the return request and route it to the mapped distributor immediately (satisfies the mandate's timing requirement). The retailer is separately prompted to attach the condition photo and confirm the counted quantity before pickup — this keeps the trigger automatic while still capturing accurate return data.

### 6.2 Pickup route optimization
- Formulated as a capacitated vehicle routing problem, solved with Google OR-Tools.
- Inputs per pending return: pickup location, estimated weight/volume, days remaining until SLA breach (urgency).
- Objective: minimize total transport cost, weighted by urgency, so returns closer to breaching their 30-day window are prioritized within the route — not just the geographically nearest stop.
- Constraints: vehicle capacity, max route duration, distributor's operating hours.
- Output: an ordered stop list written to `pickup_routes`, one row per planned trip.

### 6.3 Dispute detection & resolution
- On pickup confirmation, compare `pickups.quantity_confirmed` to `return_requests.quantity_reported`.
- If the difference exceeds a configurable tolerance (e.g. ±2% or a fixed unit count for small batches): create a `disputes` record, set status to `DISPUTED`, and block the batch from advancing.
- Resolution: both parties can attach supplementary evidence (recount photo/video). A distributor supervisor or platform admin reviews and records a final reconciled quantity. On resolution, the batch resumes at `PICKUP_CONFIRMED` using the reconciled number, and the resolution is itself written to the registry as an event.

### 6.4 Certificate issuance gate
- `POST /manufacturer/certificates` first checks for a `manufacturer_receipts` row for that batch.
- No receipt row → reject with an explicit error; no certificate is created.
- Valid receipt → certificate is created, linked to the batch number(s), and the batch transitions to `DESTROYED_CERTIFIED`. This linkage is enforced at the database level (foreign key), not just in application logic, so it can't be bypassed by a direct API call.

### 6.5 Hash-chained registry
- Every state-changing action writes one `registry_events` row: `event_type`, `actor_id`, `batch_id`, `payload` (canonical JSON of the changed fields), `created_at`.
- `hash = SHA-256(prev_hash + canonical_json(payload) + created_at)`, where `prev_hash` is the hash of the previous event in that batch's chain.
- The writing actor signs `hash` with their private key (Ed25519); the signature is stored alongside the event and verified against their registered public key in `users`.
- A periodic job (e.g. hourly) computes a Merkle root over all new events network-wide and logs the checkpoint — this is the tamper-evidence layer; no distributed ledger infrastructure is required to get it.
- A verification job periodically re-walks each batch's chain, recomputes hashes, and confirms signatures. A mismatch is flagged as an integrity breach and surfaced on the dashboard.

### 6.6 Re-entry detection
- Every `pos_transactions` insert (a sale scan) synchronously checks: is there an active registry flag on this batch number (any state from `RETURN_INITIATED` onward)?
- If yes: the transaction is marked `flagged = true`, the sale is blocked at the point of scan, a `reentry_alerts` row is created, and notifications fire to the state drug controller and the batch's manufacturer — target latency under 5 seconds from scan to alert.
- Important distinction: only sales scanned **after** the batch's `flagged_at` timestamp are treated as suspicious. Legitimate sales recorded before the batch was ever flagged are historical and must not retroactively trigger an alert — the check is time-bound, not batch-number-bound alone.

### 6.7 Compliance SLA tracking
- Each `return_requests` row tracks days elapsed since expiry. If it exceeds the mandated return window while still short of `PICKUP_CONFIRMED`, the system sets `NON_COMPLIANT` on the batch and raises it to the regulator dashboard against that retailer's license.
- The same pattern applies to the manufacturer's disposal window, measured from `manufacturer_receipts.received_at` to `destruction_certificates.issued_at`.

### 6.8 Notifications
| Trigger | Recipient(s) | Channel |
|---|---|---|
| 60-day expiry alert | Retailer | Dashboard + SMS |
| Return auto-generated | Retailer, distributor | Dashboard |
| Dispute raised | Retailer, distributor | Dashboard + SMS |
| Dispute resolved | Retailer, distributor | Dashboard |
| Certificate issued | Distributor, retailer (closure notice) | Dashboard |
| SLA breach | Regulator, offending party | Dashboard + email |
| Re-entry fraud alert | State drug controller, manufacturer | Dashboard + SMS + email |

---

## 7. Tracking dashboard

This is the control-tower view across the whole network — the single place to see everything the platform is doing at once.

**What it shows**
- Batch funnel: live counts at every lifecycle state (active → flagged → confirmed → destroyed)
- Open disputes: list, age, parties involved
- SLA compliance rate, broken down by retailer / distributor / manufacturer
- Re-entry alerts: list, status, time-to-notification
- Registry integrity status (last verification run, any flagged breaches)
- Live event feed: most recent registry events as they're written
- Network directory: retailers, distributors, manufacturers and their mappings

**Interactions**
- Filter by date range, actor, drug category, or region
- Click any batch to open its full event history (same data as the registry query, presented as a timeline)
- Export a compliance/audit report (drug name, batch number, expiry, disposal reason — matching the fields regulators already require) for a selected date range

**Access**
- Regulator and platform admin see the full network view
- Each retailer/distributor/manufacturer sees the same dashboard shell, scoped to only their own batches and events (row-level filtering by license ID)

**Data source**
- Reads from the same `registry_events` stream in near-real-time (websocket or short-poll) — the dashboard has no separate data store of its own, so it can never drift from the registry it's reporting on.

**Design direction:** light theme, bold/high-contrast typography, minimalist layout. No further UI detail is specified here — this section is intentionally about what the dashboard does, not how it looks.

---

## 8. API specification

| Method & path | Purpose |
|---|---|
| `POST /auth/login` | Authenticate, issue session token |
| `GET /retailer/batches` | List holdings with expiry status |
| `POST /retailer/pos/sale` | Log a sale scan → decrement + re-entry check |
| `POST /retailer/returns/{id}/confirm` | Attach photo/quantity to an auto-created return |
| `GET /distributor/returns/pending` | List pending returns for this distributor |
| `POST /distributor/routes/optimize` | Trigger route generation for pending returns |
| `POST /distributor/pickups/{id}/confirm` | Submit confirmed quantity + photo |
| `POST /disputes/{id}/evidence` | Attach evidence to an open dispute |
| `POST /disputes/{id}/resolve` | Record adjudicated resolution |
| `GET /manufacturer/receipts` | List confirmed batches awaiting destruction |
| `POST /manufacturer/certificates` | Upload certificate (gated on receipt) |
| `GET /registry/batches/{batch_number}/history` | Full event trail for a batch |
| `GET /registry/verify/{batch_number}` | Run/return integrity check for a batch's chain |
| `GET /alerts/reentry` | List re-entry alerts |
| `POST /alerts/reentry/{id}/resolve` | Close out an investigated alert |
| `GET /dashboard/summary` | Aggregated funnel + compliance metrics |
| `GET /dashboard/events/stream` | Live event feed (websocket) |

---

## 9. Non-functional requirements

- **Tamper evidence** — any post-write alteration to a registry event must be detectable on the next verification pass.
- **Role-based access control** — enforced at the API layer, not just hidden in the UI.
- **Auditability** — full export in the field format regulators already use (drug name, batch number, expiry date, reason for disposal).
- **Timeliness** — re-entry alerts fire within seconds of the triggering scan.
- **Resilience** — field confirmations captured offline (e.g. a distributor's pickup scan with no signal) queue locally and sync without creating duplicate registry entries.
- **Auditor independence** — the dashboard and the regulator's view read from the same registry data other actors write to; there is no separate reporting copy that could diverge from it.

---

## 10. Tech stack

| Layer | Technology |
|---|---|
| Frontend (all four surfaces) | React / Next.js, role-gated routing |
| QR/barcode scanning | Camera-based scan library (e.g. html5-qrcode) |
| API layer | FastAPI (Python) |
| Core database | PostgreSQL |
| Registry / audit log | Append-only table, SHA-256 hash chain, Ed25519 signatures |
| Route optimization | Google OR-Tools |
| Maps / distance | OpenStreetMap or Mapbox |
| Notifications | Transactional SMS/email/webhook service |
| Real-time dashboard feed | WebSocket or short-poll over the registry event stream |

---

## 11. Suggested project structure

```
/backend
  /app
    /models        (batches, users, registry_events, ...)
    /services
      route_optimizer.py
      hash_chain.py
      reentry_detector.py
      sla_tracker.py
    /api
      retailer.py
      distributor.py
      manufacturer.py
      registry.py
      dashboard.py
  /tests
/frontend
  /app              (single app, role-based routing)
    /retailer
    /distributor
    /manufacturer
    /dashboard
  /components
```

---

## 12. MVP / demo scope

- Synthetic data for a small simulated network: a handful of retailers, one distributor, one manufacturer.
- Demo drug category chosen from those already covered by CDSCO's on-pack QR mandate (antimicrobials or anti-cancer drugs), so the scanned codes reflect a real, already-existing regulatory artifact rather than an invented tag.
- Full end-to-end path (Section 5's state machine) demonstrated for at least one batch, plus one deliberately triggered re-entry attempt caught live on the dashboard.
