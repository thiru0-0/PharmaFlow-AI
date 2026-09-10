"""Deterministic seed + one-click reset for demos.

Seeded batches A-G cover every lifecycle state. All entities are synthetic — a real
deployment operates under applicable CDSCO, licensing and biomedical-waste requirements.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Batch,
    BatchHolding,
    BatchState,
    Dispute,
    DisputeEvidence,
    DestructionCertificate,
    License,
    LicenseStatus,
    ManufacturerReceipt,
    Notification,
    Pickup,
    PickupRoute,
    PickupStatus,
    PosTransaction,
    ReentryAlert,
    RegistryCheckpoint,
    RegistryEvent,
    ReturnRequest,
    ReturnStatus,
    Role,
    User,
    utcnow,
)
from app.services import batch_state, keys, registry

DEMO_PASSWORD = "demo1234"

ACCOUNTS = [
    ("Retailer A — CityCare Pharmacy", "retailer.a@pharmaflow.demo", Role.RETAILER, "Bandra, Mumbai", 19.0596, 72.8295),
    ("Retailer B — MedPlus Demo", "retailer.b@pharmaflow.demo", Role.RETAILER, "Andheri, Mumbai", 19.1136, 72.8697),
    ("Retailer C — Apollo Demo", "retailer.c@pharmaflow.demo", Role.RETAILER, "Dadar, Mumbai", 19.0176, 72.8562),
    ("Meridian Distribution Pvt Ltd", "distributor@pharmaflow.demo", Role.DISTRIBUTOR, "Kurla Depot, Mumbai", 19.0726, 72.8845),
    ("Nucleus Pharma Manufacturing", "manufacturer@pharmaflow.demo", Role.MANUFACTURER, "Taloja MIDC", 19.0800, 73.1100),
    ("State Drug Controller — Maharashtra", "regulator@pharmaflow.demo", Role.STATE_DRUG_CONTROLLER, "FDA Bhavan, Mumbai", 19.0500, 72.8300),
    ("Platform Admin", "admin@pharmaflow.demo", Role.ADMIN, "PharmaFlow Ops", 19.0600, 72.8400),
]

# Second manufacturer to demonstrate composite batch identity (same batch_number, different maker)
ACCOUNTS.append(
    ("Orbit Life Sciences", "manufacturer2@pharmaflow.demo", Role.MANUFACTURER, "Ranjangaon MIDC", 18.75, 74.25)
)

_TABLES = [
    Notification, DisputeEvidence, Dispute, DestructionCertificate, ManufacturerReceipt,
    Pickup, PickupRoute, ReentryAlert, PosTransaction, ReturnRequest,
    RegistryCheckpoint, RegistryEvent, BatchHolding, Batch, User, License,
]


def wipe(db: Session) -> None:
    for tbl in _TABLES:
        db.execute(delete(tbl))
    db.commit()


def _qr(gtin_suffix: str, expiry, batch_number: str, serial: str) -> str:
    return f"(01)0890123450{gtin_suffix}(17){expiry.strftime('%y%m%d')}(10){batch_number}(21){serial}"


def _mk_license(db, number, entity_type, state="Maharashtra", status=LicenseStatus.ACTIVE):
    lic = License(
        license_number=number, entity_type=entity_type.value if hasattr(entity_type, "value") else entity_type,
        state=state, status=status.value, valid_until=utcnow() + timedelta(days=365 * 2),
    )
    db.add(lic)
    db.flush()
    return lic


def seed(db: Session) -> dict:
    wipe(db)
    now = utcnow()

    users: dict[str, User] = {}
    for i, (name, email, role, loc, lat, lng) in enumerate(ACCOUNTS):
        lic = _mk_license(db, f"DL-{role.value[:3]}-{1000+i}", role)
        keys.ensure_keypair(lic.id)
        u = User(
            name=name, email=email, password_hash=hash_password(DEMO_PASSWORD), role=role.value,
            license_id=lic.id, public_key=keys.public_key_hex(lic.id),
            location_name=loc, lat=lat, lng=lng,
        )
        db.add(u)
        db.flush()
        users[email] = u

    ra = users["retailer.a@pharmaflow.demo"]
    rb = users["retailer.b@pharmaflow.demo"]
    rc = users["retailer.c@pharmaflow.demo"]
    dist = users["distributor@pharmaflow.demo"]
    mfr = users["manufacturer@pharmaflow.demo"]
    mfr2 = users["manufacturer2@pharmaflow.demo"]

    for r in (ra, rb, rc):
        r.mapped_distributor_id = dist.id
        r.mapped_manufacturer_id = mfr.id
    dist.mapped_manufacturer_id = mfr.id
    db.flush()

    def mk_batch(letter, drug, days_to_expiry, maker, serial):
        exp = now + timedelta(days=days_to_expiry)
        b = Batch(
            drug_name=drug, batch_number=f"AZ-2025-{letter}",
            manufacturer_license_id=maker.license_id, manufacturer_id=maker.id,
            mfg_date=now - timedelta(days=540), expiry_date=exp, category="antimicrobial",
            qr_payload=_qr(f"{ord(letter):03d}", exp, f"AZ-2025-{letter}", serial),
        )
        db.add(b)
        db.flush()
        registry.record_event(db, event_type="BATCH_MANUFACTURED", batch=b, actor=mfr if maker is mfr else mfr2,
                              payload={"drug_name": drug, "batch_number": b.batch_number,
                                       "expiry_date": str(exp), "category": "antimicrobial"})
        return b

    def hold(batch, retailer, qty, alert_sent=False):
        db.add(BatchHolding(batch_id=batch.id, retailer_id=retailer.id,
                            quantity_on_hand=qty, expiry_alert_sent=alert_sent))
        db.flush()

    # A — healthy active
    A = mk_batch("A", "Azithromycin 500mg Tablets", 180, mfr, "A0001")
    hold(A, ra, 120)
    db.add(PosTransaction(batch_id=A.id, retailer_id=ra.id, quantity=5,
                          scanned_at=now - timedelta(days=3)))

    # A' — same batch_number, different manufacturer (composite identity demo)
    Ap = mk_batch("A", "Azithromycin 250mg Suspension", 200, mfr2, "A9001")
    hold(Ap, rc, 60)

    # B — at 60-day alert threshold
    B = mk_batch("B", "Azithromycin 500mg Tablets", 60, mfr, "B0001")
    hold(B, ra, 40, alert_sent=False)

    # C — expired, auto-entered return pipeline
    C = mk_batch("C", "Azithromycin 500mg Tablets", -5, mfr, "C0001")
    hold(C, rb, 30)
    # legitimate pre-flag sale
    db.add(PosTransaction(batch_id=C.id, retailer_id=rb.id, quantity=8,
                          scanned_at=now - timedelta(days=20)))
    rrC = ReturnRequest(batch_id=C.id, retailer_id=rb.id, distributor_id=dist.id,
                        quantity_reported=22, condition="sealed", photo_url="mock://uploads/return-C.jpg",
                        status=ReturnStatus.AUTO_CREATED.value, expiry_date=C.expiry_date, confirmed_at=now)
    db.add(rrC)
    db.flush()
    batch_state.transition(db, C, BatchState.RETURN_INITIATED, actor=None,
                           event_type="RETURN_AUTO_CREATED",
                           payload={"return_request_id": rrC.id, "trigger": "expiry_crossed"})

    # H, I — extra expired returns with counted quantities so the route optimizer has a
    # genuine multi-stop problem (retailer A + retailer B, different areas).
    for letter, retailer, qty, serial, dte in [("H", ra, 45, "H0001", -6), ("I", rb, 18, "I0001", -11)]:
        bx = mk_batch(letter, "Azithromycin 500mg Tablets", dte, mfr, serial)
        hold(bx, retailer, 0)
        rrx = ReturnRequest(batch_id=bx.id, retailer_id=retailer.id, distributor_id=dist.id,
                            quantity_reported=qty, condition="sealed", photo_url=f"mock://uploads/return-{letter}.jpg",
                            status=ReturnStatus.RETURN_INITIATED.value, expiry_date=bx.expiry_date, confirmed_at=now)
        db.add(rrx)
        db.flush()
        batch_state.transition(db, bx, BatchState.RETURN_INITIATED, actor=retailer,
                               event_type="RETURN_INITIATED",
                               payload={"return_request_id": rrx.id, "quantity_reported": qty})

    # D — fraud demo: expired, still ACTIVE, retailer A holds it, will initiate return live
    D = mk_batch("D", "Azithromycin 500mg Tablets", -2, mfr, "D0001")
    hold(D, ra, 25)

    # E — dispute demo: returned + retailer-confirmed qty, pickup scheduled
    E = mk_batch("E", "Azithromycin 500mg Tablets", -8, mfr, "E0001")
    hold(E, rc, 0)
    rrE = ReturnRequest(batch_id=E.id, retailer_id=rc.id, distributor_id=dist.id,
                        quantity_reported=50, condition="sealed", photo_url="mock://uploads/return-E.jpg",
                        status=ReturnStatus.RETURN_INITIATED.value, expiry_date=E.expiry_date,
                        confirmed_at=now)
    db.add(rrE)
    db.flush()
    batch_state.transition(db, E, BatchState.RETURN_INITIATED, actor=rc,
                           event_type="RETURN_INITIATED",
                           payload={"return_request_id": rrE.id, "quantity_reported": 50})
    routeE = PickupRoute(distributor_id=dist.id, algorithm="ortools_cvrp", stops=[], vehicle_capacity=500)
    db.add(routeE)
    db.flush()
    pkE = Pickup(return_request_id=rrE.id, distributor_id=dist.id, route_id=routeE.id,
                 status=PickupStatus.SCHEDULED.value)
    db.add(pkE)
    rrE.status = ReturnStatus.PICKUP_SCHEDULED.value
    db.flush()
    batch_state.transition(db, E, BatchState.PICKUP_SCHEDULED, actor=dist,
                           event_type="PICKUP_SCHEDULED", payload={"pickup_id": pkE.id})

    # F — received by manufacturer, awaiting destruction
    F = mk_batch("F", "Azithromycin 500mg Tablets", -30, mfr, "F0001")
    hold(F, rb, 0)
    _drive_to_receipt(db, F, rb, dist, mfr, qty=75)

    # G — destroyed + certified (terminal)
    G = mk_batch("G", "Azithromycin 500mg Tablets", -45, mfr, "G0001")
    hold(G, rc, 0)
    _drive_to_receipt(db, G, rc, dist, mfr, qty=90)
    cert = DestructionCertificate(
        batch_id=G.id,
        receipt_id=db.execute(select(ManufacturerReceipt).where(ManufacturerReceipt.batch_id == G.id)).scalars().one().id,
        manufacturer_id=mfr.id, facility_name="GreenCycle Biomedical Waste Facility (synthetic)",
        cert_url="mock://uploads/cert-G.pdf", reason="expired",
    )
    db.add(cert)
    db.flush()
    batch_state.transition(db, G, BatchState.DESTROYED_CERTIFIED, actor=mfr,
                           event_type="DESTROYED_CERTIFIED",
                           payload={"certificate_id": cert.id, "facility": cert.facility_name})

    registry.build_checkpoint(db)
    db.commit()

    return {
        "accounts": [{"email": e, "password": DEMO_PASSWORD, "role": u.role, "name": u.name}
                     for e, u in users.items()],
        "batches": {b.batch_number + f" [{b.manufacturer_license_id[:8]}]": b.state
                    for b in db.execute(select(Batch)).scalars().all()},
    }


def _drive_to_receipt(db, batch, retailer, dist, mfr, qty: int):
    rr = ReturnRequest(batch_id=batch.id, retailer_id=retailer.id, distributor_id=dist.id,
                       quantity_reported=qty, condition="sealed", photo_url="mock://uploads/return.jpg",
                       status=ReturnStatus.RETURN_INITIATED.value, expiry_date=batch.expiry_date,
                       confirmed_at=utcnow())
    db.add(rr)
    db.flush()
    batch_state.transition(db, batch, BatchState.RETURN_INITIATED, actor=retailer,
                           event_type="RETURN_INITIATED", payload={"return_request_id": rr.id, "quantity_reported": qty})
    route = PickupRoute(distributor_id=dist.id, algorithm="ortools_cvrp", stops=[], vehicle_capacity=500)
    db.add(route)
    db.flush()
    pk = Pickup(return_request_id=rr.id, distributor_id=dist.id, route_id=route.id,
                quantity_confirmed=qty, photo_url="mock://uploads/pickup.jpg",
                status=PickupStatus.CONFIRMED.value, confirmed_at=utcnow())
    db.add(pk)
    rr.status = ReturnStatus.PICKUP_SCHEDULED.value
    db.flush()
    batch_state.transition(db, batch, BatchState.PICKUP_SCHEDULED, actor=dist,
                           event_type="PICKUP_SCHEDULED", payload={"pickup_id": pk.id})
    rr.status = ReturnStatus.PICKED_UP.value
    db.flush()
    batch_state.transition(db, batch, BatchState.PICKUP_CONFIRMED, actor=dist,
                           event_type="PICKUP_CONFIRMED", payload={"pickup_id": pk.id, "quantity_confirmed": qty})
    receipt = ManufacturerReceipt(batch_id=batch.id, distributor_id=dist.id, manufacturer_id=mfr.id, quantity=qty)
    db.add(receipt)
    db.flush()
    batch_state.transition(db, batch, BatchState.RECEIVED_BY_MANUFACTURER, actor=mfr,
                           event_type="RECEIVED_BY_MANUFACTURER", payload={"receipt_id": receipt.id, "quantity": qty})
