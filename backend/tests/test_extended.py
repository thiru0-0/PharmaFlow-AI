"""P1 coverage — remaining TC-01..22 beyond the 15 critical tests."""
from __future__ import annotations

from sqlalchemy import select

from app.db.base import SessionLocal
from app.models import Batch, BatchHolding, PosTransaction, User
from tests.conftest import login


def _batch(db, n, ml=None):
    q = select(Batch).where(Batch.batch_number == n)
    if ml:
        q = q.where(Batch.manufacturer_license_id == ml)
    return db.execute(q).scalars().first()


# TC-19 — role-based denial: distributor cannot upload a certificate
def test_rbac_distributor_cannot_upload_certificate(client, distributor, db):
    f = _batch(db, "AZ-2025-F")
    r = client.post("/manufacturer/certificates", headers=distributor,
                    json={"batch_id": f.id, "facility_name": "x", "cert_url": "mock://c"})
    assert r.status_code == 403


# retailer cannot resolve a dispute at adjudicator level
def test_rbac_retailer_cannot_resolve_dispute(client, distributor, retailer_c, db):
    pk = client.get("/distributor/pickups", headers=distributor).json()
    e = next(p for p in pk if p["batch_number"] == "AZ-2025-E")
    dr = client.post(f"/distributor/pickups/{e['pickup_id']}/confirm", headers=distributor,
                     json={"quantity_confirmed": 5}).json()
    r = client.post(f"/disputes/{dr['dispute_id']}/resolve", headers=retailer_c,
                    json={"reconciled_qty": 48, "resolution_notes": "no"})
    assert r.status_code == 403


# regulator is read-only — cannot record a sale
def test_regulator_is_read_only(client, regulator, db):
    a = _batch(db, "AZ-2025-A")
    r = client.post("/retailer/pos/sale", headers=regulator, json={"qr_payload": a.qr_payload, "quantity": 1})
    assert r.status_code == 403


# a retailer cannot see another retailer's batches
def test_tenant_isolation_batches(client, retailer_a, db):
    rows = client.get("/retailer/batches", headers=retailer_a).json()
    nums = {b["batch_number"] for b in rows}
    assert "AZ-2025-C" not in nums  # C is held by retailer B


# TC-15 — certificate for an unknown batch number is rejected
def test_certificate_unknown_batch(client, manufacturer):
    r = client.post("/manufacturer/certificates", headers=manufacturer,
                    json={"batch_id": "does-not-exist", "facility_name": "x", "cert_url": "mock://c"})
    assert r.status_code in (404, 403)


# TC-02 / expiry alert idempotency — running the job twice does not duplicate
def test_expiry_alert_idempotent(client, admin, db):
    r1 = client.post("/demo/jobs/expiry", headers=admin).json()
    r2 = client.post("/demo/jobs/expiry", headers=admin).json()
    # second run creates nothing new
    assert r2["alerts_sent"] == 0
    assert r2["returns_created"] == 0
    notifs = client.get("/dashboard/notifications", headers=login(client, "retailer.a@pharmaflow.demo")).json()
    # one alert per channel (in_app + sms), never re-sent — so exactly one per channel
    sixty_in_app = [n for n in notifs if n["type"] == "EXPIRY_60_DAY"
                    and n["payload"].get("batch_number") == "AZ-2025-B" and n["channel"] == "in_app"]
    assert len(sixty_in_app) == 1


# TC-01 / TC-08 — full happy path leaves an unbroken ordered trail
def test_full_lifecycle_audit_trail(client, admin, regulator):
    res = client.post("/demo/scripts/happy", headers=admin).json()
    assert res["final_state"] == "DESTROYED_CERTIFIED"
    assert res["registry_valid"] is True
    hist = client.get("/registry/batches/AZ-2025-A/history?manufacturer_license_id="
                      + _mlid(client, regulator, "AZ-2025-A"), headers=regulator).json()
    types = [e["event_type"] for e in hist["events"]]
    for step in ["RETURN_INITIATED", "PICKUP_CONFIRMED", "RECEIVED_BY_MANUFACTURER", "DESTROYED_CERTIFIED"]:
        assert step in types
    assert [e["seq"] for e in hist["events"]] == sorted(e["seq"] for e in hist["events"])


def _mlid(client, hdr, batch_no):
    for b in client.get("/dashboard/batches", headers=hdr).json():
        if b["batch_number"] == batch_no and b["state"] != "ACTIVE":
            return b["manufacturer_license_id"]
    # fall back to first
    return client.get("/dashboard/batches", headers=hdr).json()[0]["manufacturer_license_id"]


# TC-13 — non-compliance detection escalates to the regulator
def test_sla_breach_flags_non_compliant(client, admin, db):
    # push batch C's return well past the window
    s = SessionLocal()
    from app.models import ReturnRequest, utcnow
    from datetime import timedelta
    rr = s.execute(select(ReturnRequest).join(Batch, Batch.id == ReturnRequest.batch_id)
                   .where(Batch.batch_number == "AZ-2025-C")).scalars().first()
    rr.expiry_date = utcnow() - timedelta(days=90)
    s.add(rr); s.commit(); s.close()
    out = client.post("/demo/jobs/sla", headers=admin).json()
    assert out["count"] >= 1
    c = _batch(SessionLocal(), "AZ-2025-C")
    assert c.non_compliant is True


# re-entry alert resolution appends an event, never erases the alert
def test_reentry_resolution_appends(client, retailer_a, retailer_b, regulator, db):
    b = client.get("/retailer/batches", headers=retailer_a).json()
    d = next(x for x in b if x["batch_number"] == "AZ-2025-D")
    client.post(f"/retailer/batches/{d['batch_id']}/initiate-return", headers=retailer_a,
                json={"quantity_reported": 25, "condition": "sealed"})
    dd = _batch(db, "AZ-2025-D")
    client.post("/retailer/pos/sale", headers=retailer_b, json={"qr_payload": dd.qr_payload, "quantity": 3})
    alerts = client.get("/alerts/reentry", headers=regulator).json()
    aid = alerts[0]["id"]
    r = client.post(f"/alerts/reentry/{aid}/resolve", headers=regulator, json={"resolution_notes": "investigated"})
    assert r.status_code == 200
    again = client.get(f"/alerts/reentry/{aid}", headers=regulator).json()
    assert again["status"] == "RESOLVED"
    assert again["resolution_notes"] == "investigated"


# initiating/confirming a return must pull the counted quantity out of on-hand inventory
# immediately, and pickup confirmation later must never touch it again.
def test_return_deducts_inventory_immediately(client, retailer_a, distributor, admin, db):
    before = client.get("/retailer/batches", headers=retailer_a).json()
    d = next(x for x in before if x["batch_number"] == "AZ-2025-D")
    on_hand_before = d["quantity_on_hand"]
    assert on_hand_before > 0

    r = client.post(f"/retailer/batches/{d['batch_id']}/initiate-return", headers=retailer_a,
                    json={"quantity_reported": on_hand_before, "condition": "sealed"})
    assert r.status_code == 201
    assert r.json()["remaining_on_hand"] == 0

    after = client.get("/retailer/batches", headers=retailer_a).json()
    d_after = next(x for x in after if x["batch_number"] == "AZ-2025-D")
    assert d_after["quantity_on_hand"] == 0  # left the shelf the instant the return was counted

    # can't report more than what's actually left
    r2 = client.post(f"/retailer/batches/{d['batch_id']}/initiate-return", headers=retailer_a,
                     json={"quantity_reported": 5, "condition": "sealed"})
    assert r2.status_code == 409  # already open, blocked before any further deduction

    # pickup confirmation must not touch the retailer's inventory a second time
    pending = client.get("/distributor/returns/pending", headers=distributor).json()
    p = next(x for x in pending if x["batch_number"] == "AZ-2025-D")
    client.post("/distributor/routes/optimize", headers=distributor, json={"vehicle_capacity": 500})
    pickups = client.get("/distributor/pickups", headers=distributor).json()
    pk = next(x for x in pickups if x["batch_number"] == "AZ-2025-D")
    client.post(f"/distributor/pickups/{pk['pickup_id']}/confirm", headers=distributor,
                json={"quantity_confirmed": on_hand_before})

    final = client.get("/retailer/batches", headers=retailer_a).json()
    d_final = next(x for x in final if x["batch_number"] == "AZ-2025-D")
    assert d_final["quantity_on_hand"] == 0  # unchanged by the pickup step


def test_insufficient_stock_blocks_return(client, retailer_a, db):
    b = client.get("/retailer/batches", headers=retailer_a).json()
    d = next(x for x in b if x["batch_number"] == "AZ-2025-D")
    r = client.post(f"/retailer/batches/{d['batch_id']}/initiate-return", headers=retailer_a,
                    json={"quantity_reported": d["quantity_on_hand"] + 1000, "condition": "sealed"})
    assert r.status_code == 409
    unchanged = client.get("/retailer/batches", headers=retailer_a).json()
    assert next(x for x in unchanged if x["batch_number"] == "AZ-2025-D")["quantity_on_hand"] == d["quantity_on_hand"]
