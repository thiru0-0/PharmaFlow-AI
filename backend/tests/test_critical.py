"""The 15 non-negotiable P0 tests (Build Spec Section 13.2)."""
from __future__ import annotations

import concurrent.futures

from sqlalchemy import select

from app.db.base import SessionLocal
from app.models import Batch, BatchHolding, BatchState, License, PosTransaction, User, utcnow
from tests.conftest import login


def _batch(db, number, maker_license=None):
    q = select(Batch).where(Batch.batch_number == number)
    if maker_license:
        q = q.where(Batch.manufacturer_license_id == maker_license)
    return db.execute(q).scalars().first()


def _initiate_return_D(client, hdr):
    b = client.get("/retailer/batches", headers=hdr).json()
    d = next(x for x in b if x["batch_number"] == "AZ-2025-D")
    return client.post(f"/retailer/batches/{d['batch_id']}/initiate-return", headers=hdr,
                       json={"quantity_reported": 25, "condition": "sealed"})


# 1
def test_returned_batch_cannot_be_sold(client, retailer_a, retailer_b, db):
    assert _initiate_return_D(client, retailer_a).status_code == 201
    d = _batch(db, "AZ-2025-D")
    r = client.post("/retailer/pos/sale", headers=retailer_b,
                    json={"qr_payload": d.qr_payload, "quantity": 5})
    assert r.status_code == 409
    assert r.json()["detail"]["status"] == "BLOCKED_REENTRY"


# 2
def test_preflag_sale_no_fraud(client, retailer_b, db):
    # Batch C had a legitimate pre-flag sale seeded; it is now RETURN_INITIATED.
    c = _batch(db, "AZ-2025-C")
    pre = db.execute(
        select(PosTransaction).where(PosTransaction.batch_id == c.id, PosTransaction.flagged == False)  # noqa: E712
    ).scalars().all()
    assert len(pre) >= 1
    assert all(not t.flagged for t in pre)
    alerts = client.get("/alerts/reentry", headers=login(client, "regulator@pharmaflow.demo")).json()
    assert all(a["batch_number"] != "AZ-2025-C" for a in alerts)


# 3
def test_postflag_sale_triggers_fraud(client, retailer_a, retailer_b, db):
    _initiate_return_D(client, retailer_a)
    d = _batch(db, "AZ-2025-D")
    client.post("/retailer/pos/sale", headers=retailer_b,
                json={"qr_payload": d.qr_payload, "quantity": 5})
    reg = login(client, "regulator@pharmaflow.demo")
    alerts = client.get("/alerts/reentry", headers=reg).json()
    assert any(a["batch_number"] == "AZ-2025-D" for a in alerts)


# 4
def test_fraud_alert_reaches_manufacturer(client, retailer_a, retailer_b, db):
    _initiate_return_D(client, retailer_a)
    d = _batch(db, "AZ-2025-D")
    client.post("/retailer/pos/sale", headers=retailer_b,
                json={"qr_payload": d.qr_payload, "quantity": 5})
    mfr = login(client, "manufacturer@pharmaflow.demo")
    notifs = client.get("/dashboard/notifications", headers=mfr).json()
    assert any(n["type"] == "REENTRY_FRAUD" for n in notifs)
    alerts = client.get("/alerts/reentry", headers=mfr).json()
    assert any(a["batch_number"] == "AZ-2025-D" and a["notified_manufacturer"] for a in alerts)


# 5
def test_fraud_alert_reaches_regulator(client, retailer_a, retailer_b, db):
    _initiate_return_D(client, retailer_a)
    d = _batch(db, "AZ-2025-D")
    client.post("/retailer/pos/sale", headers=retailer_b,
                json={"qr_payload": d.qr_payload, "quantity": 5})
    reg = login(client, "regulator@pharmaflow.demo")
    notifs = client.get("/dashboard/notifications", headers=reg).json()
    assert any(n["type"] == "REENTRY_FRAUD" for n in notifs)


# 6
def test_quantity_mismatch_creates_dispute(client, distributor, db):
    pickups = client.get("/distributor/pickups", headers=distributor).json()
    e = next(p for p in pickups if p["batch_number"] == "AZ-2025-E")
    r = client.post(f"/distributor/pickups/{e['pickup_id']}/confirm", headers=distributor,
                    json={"quantity_confirmed": 10})
    assert r.status_code == 200
    assert r.json()["status"] == "DISPUTED"


# 7
def test_disputed_batch_cannot_advance(client, distributor, manufacturer, db):
    pickups = client.get("/distributor/pickups", headers=distributor).json()
    e = next(p for p in pickups if p["batch_number"] == "AZ-2025-E")
    client.post(f"/distributor/pickups/{e['pickup_id']}/confirm", headers=distributor,
                json={"quantity_confirmed": 10})
    eb = _batch(db, "AZ-2025-E")
    r = client.post("/manufacturer/receipts", headers=manufacturer,
                    json={"batch_id": eb.id, "quantity": 50})
    assert r.status_code == 409


# 8
def test_resolved_dispute_can_advance(client, distributor, admin, manufacturer, db):
    pickups = client.get("/distributor/pickups", headers=distributor).json()
    e = next(p for p in pickups if p["batch_number"] == "AZ-2025-E")
    dr = client.post(f"/distributor/pickups/{e['pickup_id']}/confirm", headers=distributor,
                     json={"quantity_confirmed": 10}).json()
    res = client.post(f"/disputes/{dr['dispute_id']}/resolve", headers=admin,
                      json={"reconciled_qty": 48, "resolution_notes": "recount agreed"})
    assert res.status_code == 200
    assert res.json()["batch_state"] == "PICKUP_CONFIRMED"


# 9
def test_certificate_without_receipt_fails(client, manufacturer, db):
    f = _batch(db, "AZ-2025-F")  # RECEIVED_BY_MANUFACTURER has a receipt; use E instead
    e = _batch(db, "AZ-2025-E")
    r = client.post("/manufacturer/certificates", headers=manufacturer,
                    json={"batch_id": e.id, "facility_name": "X", "cert_url": "mock://c.pdf"})
    assert r.status_code == 409
    assert "receipt not found" in r.json()["detail"]


# 10
def test_certificate_with_receipt_succeeds(client, manufacturer, db):
    f = _batch(db, "AZ-2025-F")
    r = client.post("/manufacturer/certificates", headers=manufacturer,
                    json={"batch_id": f.id, "facility_name": "GreenCycle (synthetic)",
                          "cert_url": "mock://cert-F.pdf"})
    assert r.status_code == 201, r.text
    assert r.json()["batch_state"] == "DESTROYED_CERTIFIED"


# 11
def test_hash_tampering_detected(client, regulator, db):
    g = _batch(db, "AZ-2025-G")
    from app.models import RegistryEvent

    s = SessionLocal()
    ev = s.execute(select(RegistryEvent).where(RegistryEvent.batch_id == g.id)).scalars().all()[1]
    ev.payload = {**ev.payload, "quantity": 999999}
    s.add(ev)
    s.commit()
    s.close()
    v = client.get("/registry/verify/AZ-2025-G", headers=regulator).json()
    assert v["valid"] is False
    assert v["hash_chain_valid"] is False


# 12
def test_signature_tampering_detected(client, regulator, db):
    g = _batch(db, "AZ-2025-G")
    from app.models import RegistryEvent

    s = SessionLocal()
    ev = s.execute(select(RegistryEvent).where(RegistryEvent.batch_id == g.id)).scalars().first()
    ev.signature = "00" * 64
    s.add(ev)
    s.commit()
    s.close()
    v = client.get("/registry/verify/AZ-2025-G", headers=regulator).json()
    assert v["signatures_valid"] is False
    assert v["valid"] is False


# 13
def test_duplicate_return_blocked(client, retailer_a, db):
    assert _initiate_return_D(client, retailer_a).status_code == 201
    r2 = _initiate_return_D(client, retailer_a)
    assert r2.status_code == 409
    assert "already open" in r2.json()["detail"]["message"]


# 14
def test_two_manufacturers_same_batch_number(client, regulator, db):
    rows = db.execute(select(Batch).where(Batch.batch_number == "AZ-2025-A")).scalars().all()
    assert len(rows) == 2
    assert rows[0].manufacturer_license_id != rows[1].manufacturer_license_id
    # history is disambiguated by manufacturer_license_id
    v0 = client.get(f"/registry/verify/AZ-2025-A?manufacturer_license_id={rows[0].manufacturer_license_id}",
                    headers=regulator)
    assert v0.status_code == 200
    ambiguous = client.get("/registry/verify/AZ-2025-A", headers=regulator)
    assert ambiguous.status_code == 409


# 15
def test_concurrent_sales_cannot_go_negative(client, retailer_a, db):
    a = db.execute(
        select(Batch).join(BatchHolding, BatchHolding.batch_id == Batch.id)
        .where(Batch.batch_number == "AZ-2025-A", BatchHolding.retailer_id ==
               db.execute(select(User.id).where(User.email == "retailer.a@pharmaflow.demo")).scalar_one())
    ).scalars().first()
    holding = db.execute(select(BatchHolding).where(BatchHolding.batch_id == a.id)).scalars().first()
    start_qty = holding.quantity_on_hand

    def sell():
        return client.post("/retailer/pos/sale", headers=retailer_a,
                           json={"qr_payload": a.qr_payload, "quantity": 20})

    n = (start_qty // 20) + 5  # more attempts than stock allows
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = [f.result().status_code for f in [ex.submit(sell) for _ in range(n)]]

    s = SessionLocal()
    final = s.execute(select(BatchHolding).where(BatchHolding.batch_id == a.id)).scalars().first().quantity_on_hand
    s.close()
    assert final >= 0
    assert results.count(201) <= start_qty // 20
