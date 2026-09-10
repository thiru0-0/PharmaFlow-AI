# PharmaFlow AI — Reverse Chain Compliance Platform
### Requirements & Test Specification (PS3 — CDSCO Drug Disposal Mandate)

---

## 1. Overview

PharmaFlow operationalizes India's CDSCO 2025 drug disposal mandate. It gives four parties — retailer, distributor, manufacturer, and the state drug controller — a shared, batch-level view of every expired/unused medicine as it moves from a pharmacy shelf to verified destruction. A hash-chained shared registry records every handoff, and a re-entry detection layer catches any "returned" batch that resurfaces for sale at any pharmacy in the network.

The platform does not take physical custody of drugs at any point — it is a coordination and record-keeping layer that connects systems each licensed party already operates (or would operate under this mandate).

---

## 2. Actors

| Actor | Role |
|---|---|
| Retailer (pharmacist / pharmacy staff) | Sells stock, flags near-expiry batches, initiates returns |
| Distributor | Collects returns from mapped retailers, verifies and forwards to manufacturer |
| Manufacturer | Accepts confirmed returns, arranges destruction, issues certificates |
| State drug controller | Read-only oversight; receives compliance and fraud alerts |
| System (automated) | Registry service, re-entry detection service, pickup route optimizer |

---

## 3. Functional requirements

### 3.1 Retailer module
- **FR-1.1** — POS scans the batch QR/barcode at every sale and decrements that batch's remaining count in real time.
- **FR-1.2** — System alerts the pharmacist when a batch reaches 60 days to expiry.
- **FR-1.3** — System auto-generates a return request to the retailer's mapped distributor when a batch crosses its expiry date.
- **FR-1.4** — Retailer must log batch number (via QR scan), quantity, and a condition photo when initiating a return.
- **FR-1.5** — POS must block a sale of any batch flagged "in return pipeline" or "destroyed" in the registry, and immediately trigger a re-entry alert.

### 3.2 Distributor module
- **FR-2.1** — Distributor dashboard lists all pending return requests from mapped retailers.
- **FR-2.2** — System recommends an optimized pickup route/batching across multiple pending retailer returns (reuses the transfer-scoring engine, repointed at pickup logistics).
- **FR-2.3** — Distributor confirms pickup with a weight-verified photo and a batch QR scan.
- **FR-2.4** — If the distributor-confirmed quantity differs from the retailer-logged quantity beyond a defined tolerance, the system raises a dispute flag automatically.
- **FR-2.5** — A batch cannot progress to "confirmed — in transit to manufacturer" status while a dispute on it is open.
- **FR-2.6** — System tracks each batch's remaining time against the regulatory return window and flags any at risk of breaching it.

### 3.3 Manufacturer module
- **FR-3.1** — Manufacturer dashboard lists confirmed batches received from distributor(s).
- **FR-3.2** — Manufacturer can schedule pickup with an authorized biomedical-waste facility.
- **FR-3.3** — Manufacturer can upload a destruction certificate for a batch **only if** that batch has a prior confirmed-receipt record in the system — the system must block certificate issuance otherwise.
- **FR-3.4** — Every certificate is linked to the specific batch number(s) it covers; partial or unlinked certificates are not permitted.
- **FR-3.5** — On certificate upload, the system auto-populates a disposal record (drug name, batch number, expiry date, reason for disposal) for regulatory record-keeping.

### 3.4 Shared registry & re-entry detection
- **FR-4.1** — Every event (return initiated, pickup confirmed, dispute raised/resolved, certificate issued) is written to an append-only, hash-chained record, digitally signed by the party that created it.
- **FR-4.2** — A batch is marked "flagged" in the registry the moment a return is initiated on it.
- **FR-4.3** — Any POS scan of a flagged batch number, at any retailer, triggers an immediate alert.
- **FR-4.4** — Alerts are routed to the state drug controller and the original manufacturer in real time.
- **FR-4.5** — Registry is queryable by batch number, retailer, distributor, manufacturer, and date range.

### 3.5 Regulator (state drug controller)
- **FR-5.1** — Read-only dashboard showing compliance status by retailer/distributor/manufacturer, open disputes, and fraud alerts.
- **FR-5.2** — Can pull a full, chronological event history for any batch number.

---

## 4. Non-functional requirements

- **Tamper evidence** — hash-chained registry; any post-write alteration must be detectable.
- **Role-based access control** — each actor can only act within their own role's permissions.
- **Auditability** — full event history exportable in a format matching CDSCO's disposal record fields (drug name, batch number, expiry date, reason for disposal).
- **Timeliness** — re-entry alerts fire within seconds of the triggering POS scan, not on a batch job.
- **Resilience** — pickup/return confirmations captured in the field (possibly offline) must not be lost or duplicated on sync.
- **MVP scope** — synthetic/simulated data; demo built around a drug category already covered by CDSCO's QR/barcode mandate (e.g. antimicrobials or anti-cancer drugs), so scanned codes are realistic rather than invented.

---

## 5. End-to-end flow (happy path)

1. Pharmacy A sells units of Batch X; each sale scan decrements the batch's remaining count.
2. At 60 days to expiry, Pharmacy A's pharmacist is alerted.
3. Batch X crosses its expiry date — the system auto-generates a return request to Pharmacy A's mapped distributor.
4. Pharmacist logs the remaining quantity, batch photo, and condition; request status becomes "return initiated," and Batch X is flagged in the shared registry.
5. The distributor's dashboard shows the request; the route optimizer batches it with other pending pickups in the area.
6. On pickup, the distributor scans Batch X's QR and logs a weight-verified photo.
7. Logged quantity matches confirmed quantity — no dispute. Batch X status becomes "confirmed — in transit to manufacturer."
8. The manufacturer receives the confirmed batch and schedules pickup with an authorized biomedical-waste facility.
9. After destruction, the manufacturer uploads a certificate linked to Batch X's batch number. The system verifies a confirmed-receipt record exists before accepting it.
10. Batch X's registry entry is closed as "destroyed," with the full retailer → distributor → manufacturer → certificate trail preserved.
11. In parallel, throughout this entire process, any attempt to sell Batch X at any pharmacy's POS is checked against the registry and would trigger an immediate re-entry alert.

---

## 6. Test cases

### 6.1 Core / happy path

| ID | Scenario | Steps | Expected result |
|---|---|---|---|
| TC-01 | Full compliant batch lifecycle | Run steps 1–10 above | Batch reaches "destroyed" status with an unbroken, correctly ordered event trail |
| TC-02 | 60-day expiry alert | Set a batch's expiry to 60 days out | Pharmacist receives an alert; batch not yet flagged for return |
| TC-03 | Auto return-request on expiry | Advance batch past its expiry date | Return request auto-created and assigned to the mapped distributor |
| TC-04 | Retailer return logging | Initiate a return, attach photo, enter quantity | Batch flagged "in return pipeline" in the registry |
| TC-05 | Optimized pickup batching | 3 retailers in the same area have pending returns | Distributor sees one recommended route covering all 3, not 3 separate trips |
| TC-06 | Matched pickup confirmation | Distributor confirms the same quantity the retailer logged | No dispute; batch proceeds to "confirmed" |
| TC-07 | Certificate issuance | Manufacturer uploads a certificate for a confirmed batch | Certificate accepted, linked to the batch, registry closes the batch |
| TC-08 | Full audit trail | Query a destroyed batch's history | Every step (return, pickup, confirmation, certificate) visible with timestamps and signer identity |

### 6.2 Edge cases — "what if" scenarios

| ID | Scenario | Expected result |
|---|---|---|
| TC-09 | Distributor-confirmed quantity doesn't match retailer-logged quantity | Dispute flag raised automatically; batch blocked from progressing until resolved |
| TC-10 | Manufacturer tries to upload a certificate with no prior confirmed receipt | Upload rejected with a clear error; certificate not created |
| TC-11 | A flagged (returned) batch is scanned for sale at a different pharmacy | Sale blocked at POS; alert fires immediately to the state drug controller and the manufacturer |
| TC-12 | A batch is only partially returned (some units already legitimately sold before it was flagged) | Registry distinguishes "sold pre-flag" from "returned," and does not fire a false re-entry alert on the already-sold units |
| TC-13 | Retailer never initiates a return within the mandated post-expiry window | System auto-raises a non-compliance flag against the retailer, visible on the regulator dashboard |
| TC-14 | Two different manufacturers happen to use the same batch number | Registry key is (manufacturer license ID + batch number), so no collision or cross-contamination occurs |
| TC-15 | A certificate is submitted referencing a batch number never logged in the registry | Rejected as invalid; flagged for manual review rather than silently accepted |
| TC-16 | Distributor's device is offline during a pickup scan | Scan is queued locally with original timestamp, synced on reconnect, no duplicate or lost registry entry |
| TC-17 | A dispute needs resolution | Both parties submit evidence (recount, photo); a supervisor adjudicates; registry updates with the final reconciled quantity and resolution note |
| TC-18 | Retailer accidentally submits two return requests for the same batch | Second submission is detected as a duplicate and blocked, with a message pointing to the existing open request |

### 6.3 Non-functional / security

| ID | Scenario | Expected result |
|---|---|---|
| TC-19 | A distributor account attempts a manufacturer-only action (certificate upload) | Access denied by role-based permissions |
| TC-20 | A registry record is altered after being written | Hash-chain validation fails on the next check; integrity breach flagged for investigation |
| TC-21 | High volume of concurrent POS scans across many retailers | Re-entry check stays within target response time under load; no scan silently dropped |
| TC-22 | State drug controller queries a batch's complete cross-actor history | Returns a complete, chronologically ordered trail spanning all four actors |

---

## 7. Out of scope for hackathon MVP

- Real integration with third-party pharmacy billing software (roadmap item; MVP uses a purpose-built scan app for pilot retailers).
- On-chain anchoring of registry checkpoints (mentioned as a credibility/roadmap item, not required for the demo).
- Full national multi-state rollout — demo operates on a small simulated network (a handful of retailers, one distributor, one manufacturer).
