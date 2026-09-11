"""Server-side scripted demo runners. Execute the real flow against the DB and time it.

These call the same service layer the HTTP endpoints use, so a judge refreshing the
browser afterwards sees the persisted result.
"""
from __future__ import annotations

import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Batch,
    BatchState,
    BatchHolding,
    ManufacturerReceipt,
    Pickup,
    PickupStatus,
    PosTransaction,
    ReturnRequest,
    ReturnStatus,
    Role,
    User,
    utcnow,
)
from app.services import batch_state, reentry, registry


def _u(db, email) -> User:
    return db.execute(select(User).where(User.email == email)).scalars().one()


def _batch(db, number, maker_license=None) -> Batch:
    q = select(Batch).where(Batch.batch_number == number)
    if maker_license:
        q = q.where(Batch.manufacturer_license_id == maker_license)
    return db.execute(q).scalars().first()


def run_fraud(db: Session) -> dict:
    t0 = time.perf_counter()
    steps = []
    ra = _u(db, "retailer.a@pharmaflow.demo")
    rb = _u(db, "retailer.b@pharmaflow.demo")
    D = _batch(db, "AZ-2025-D")
    if D.state != BatchState.ACTIVE.value:
        raise HTTPException(409, "Batch D not in ACTIVE state — run demo reset first")

    # 1. Retailer A initiates return on Batch D
    holding_a = db.execute(
        select(BatchHolding).where(BatchHolding.batch_id == D.id, BatchHolding.retailer_id == ra.id)
    ).scalars().first()
    returned_qty = min(25, holding_a.quantity_on_hand) if holding_a else 25
    rr = db.execute(
        select(ReturnRequest).where(ReturnRequest.batch_id == D.id, ReturnRequest.retailer_id == ra.id)
    ).scalars().first() or ReturnRequest(
        batch_id=D.id, retailer_id=ra.id, distributor_id=ra.mapped_distributor_id, expiry_date=D.expiry_date
    )
    rr.quantity_reported = returned_qty
    rr.condition = "sealed"
    rr.photo_url = "mock://uploads/return-D.jpg"
    rr.status = ReturnStatus.RETURN_INITIATED.value
    rr.confirmed_at = utcnow()
    db.add(rr)
    if holding_a:
        holding_a.quantity_on_hand -= returned_qty
        db.add(holding_a)
    db.flush()
    batch_state.transition(db, D, BatchState.RETURN_INITIATED, actor=ra,
                           event_type="RETURN_INITIATED",
                           payload={"return_request_id": rr.id, "quantity_reported": returned_qty, "trigger": "manual"})
    db.commit()
    steps.append({"step": "Retailer A initiates return on Batch D",
                  "result": f"state={D.state}, flagged_at={D.flagged_at.isoformat()}"})

    # 2. Retailer B scans the same batch for sale
    txn = PosTransaction(batch_id=D.id, retailer_id=rb.id, quantity=10, scanned_at=utcnow())
    db.add(txn)
    db.flush()
    alert = reentry.check_and_handle(db, batch=D, retailer=rb, quantity=10, pos_txn=txn)
    db.commit()
    if not alert:
        raise HTTPException(500, "Re-entry check did not fire")
    steps.append({
        "step": "Retailer B scans Batch D at POS",
        "result": "SALE BLOCKED — re-entry alert raised",
        "alert_id": alert.id,
        "notified_controller": alert.notified_controller,
        "notified_manufacturer": alert.notified_manufacturer,
        "notification_latency_ms": alert.notification_latency_ms,
    })

    elapsed = round(time.perf_counter() - t0, 2)
    return {"scenario": "fraud", "elapsed_seconds": elapsed, "under_60s": elapsed < 60,
            "alert_id": alert.id, "steps": steps}


def run_happy(db: Session) -> dict:
    """Drive a fresh healthy batch (A) through the full lifecycle to DESTROYED_CERTIFIED."""
    t0 = time.perf_counter()
    steps = []
    ra = _u(db, "retailer.a@pharmaflow.demo")
    dist = _u(db, "distributor@pharmaflow.demo")
    mfr = _u(db, "manufacturer@pharmaflow.demo")
    A = db.execute(
        select(Batch).where(Batch.batch_number == "AZ-2025-A", Batch.manufacturer_id == mfr.id)
    ).scalars().one()
    if A.state != BatchState.ACTIVE.value:
        raise HTTPException(409, "Batch A not ACTIVE — run demo reset first")

    holding = db.execute(
        select(BatchHolding).where(BatchHolding.batch_id == A.id, BatchHolding.retailer_id == ra.id)
    ).scalars().one()

    # 1. sale decrements stock
    before = holding.quantity_on_hand
    txn = PosTransaction(batch_id=A.id, retailer_id=ra.id, quantity=3, scanned_at=utcnow())
    db.add(txn)
    holding.quantity_on_hand -= 3
    registry.record_event(db, event_type="POS_SALE", batch=A, actor=ra,
                          payload={"quantity": 3, "remaining_on_hand": holding.quantity_on_hand})
    db.commit()
    steps.append({"step": "Retailer sells 3 units", "result": f"stock {before} -> {holding.quantity_on_hand}"})

    # 2. force expiry -> return initiated (all remaining stock leaves active inventory)
    A.expiry_date = utcnow()
    returned_qty = holding.quantity_on_hand
    rr = ReturnRequest(batch_id=A.id, retailer_id=ra.id, distributor_id=dist.id,
                       quantity_reported=returned_qty, condition="sealed",
                       photo_url="mock://uploads/return-A.jpg",
                       status=ReturnStatus.RETURN_INITIATED.value, expiry_date=A.expiry_date,
                       confirmed_at=utcnow())
    db.add(rr)
    holding.quantity_on_hand = 0
    db.add(holding)
    db.flush()
    batch_state.transition(db, A, BatchState.RETURN_INITIATED, actor=ra, event_type="RETURN_INITIATED",
                           payload={"return_request_id": rr.id, "quantity_reported": rr.quantity_reported})
    db.commit()
    steps.append({"step": "Expiry crossed -> return auto-initiated",
                  "result": f"state={A.state}, flagged, {returned_qty} units left inventory (on-hand -> 0)"})

    # 3. distributor optimized route + pickup (qty matches)
    from app.services.route_optimizer import Stop, optimize

    opt = optimize((dist.lat, dist.lng),
                   [Stop(ra.id, ra.name, ra.lat, ra.lng, rr.quantity_reported, 0.8)], 500)
    from app.models import PickupRoute

    route = PickupRoute(distributor_id=dist.id, algorithm=opt["algorithm"], stops=opt["stops"],
                        total_distance_km=opt["total_distance_km"], total_cost=opt["total_cost"],
                        vehicle_capacity=opt["vehicle_capacity"], capacity_used=opt["capacity_used"],
                        urgency_score=opt["urgency_score"])
    db.add(route)
    db.flush()
    pk = Pickup(return_request_id=rr.id, distributor_id=dist.id, route_id=route.id,
                status=PickupStatus.SCHEDULED.value)
    db.add(pk)
    db.flush()
    batch_state.transition(db, A, BatchState.PICKUP_SCHEDULED, actor=dist, event_type="PICKUP_SCHEDULED",
                           payload={"route_id": route.id, "algorithm": opt["algorithm"]})
    pk.quantity_confirmed = rr.quantity_reported
    pk.status = PickupStatus.CONFIRMED.value
    pk.confirmed_at = utcnow()
    pk.photo_url = "mock://uploads/pickup-A.jpg"
    db.flush()
    batch_state.transition(db, A, BatchState.PICKUP_CONFIRMED, actor=dist, event_type="PICKUP_CONFIRMED",
                           payload={"pickup_id": pk.id, "quantity_confirmed": pk.quantity_confirmed,
                                    "within_tolerance": True})
    db.commit()
    steps.append({"step": "Distributor optimizes route + confirms pickup (qty matches)",
                  "result": f"state={A.state}, algorithm={opt['algorithm']}, "
                            f"route_cost={opt['total_cost']}"})

    # 4. manufacturer receipt
    receipt = ManufacturerReceipt(batch_id=A.id, distributor_id=dist.id, manufacturer_id=mfr.id,
                                  quantity=pk.quantity_confirmed)
    db.add(receipt)
    db.flush()
    batch_state.transition(db, A, BatchState.RECEIVED_BY_MANUFACTURER, actor=mfr,
                           event_type="RECEIVED_BY_MANUFACTURER", payload={"receipt_id": receipt.id})
    db.commit()
    steps.append({"step": "Manufacturer confirms receipt", "result": f"state={A.state}"})

    # 5. destruction certificate -> terminal
    from app.models import DestructionCertificate

    cert = DestructionCertificate(batch_id=A.id, receipt_id=receipt.id, manufacturer_id=mfr.id,
                                  facility_name="GreenCycle Biomedical Waste Facility (synthetic)",
                                  cert_url="mock://uploads/cert-A.pdf", reason="expired")
    db.add(cert)
    db.flush()
    batch_state.transition(db, A, BatchState.DESTROYED_CERTIFIED, actor=mfr,
                           event_type="DESTROYED_CERTIFIED", payload={"certificate_id": cert.id})
    db.commit()
    steps.append({"step": "Manufacturer uploads destruction certificate", "result": f"state={A.state}"})

    verification = registry.verify_batch_chain(db, A)
    elapsed = round(time.perf_counter() - t0, 2)
    return {"scenario": "happy", "elapsed_seconds": elapsed, "under_60s": elapsed < 60,
            "final_state": A.state, "registry_valid": verification["valid"], "steps": steps}


def run_dispute(db: Session) -> dict:
    t0 = time.perf_counter()
    steps = []
    dist = _u(db, "distributor@pharmaflow.demo")
    E = _batch(db, "AZ-2025-E")
    if E.state != BatchState.PICKUP_SCHEDULED.value:
        raise HTTPException(409, "Batch E not PICKUP_SCHEDULED — run demo reset first")
    pk = db.execute(
        select(Pickup).join(ReturnRequest, ReturnRequest.id == Pickup.return_request_id)
        .where(ReturnRequest.batch_id == E.id)
    ).scalars().first()
    rr = db.get(ReturnRequest, pk.return_request_id)
    from app.core.config import settings

    reported = rr.quantity_reported
    confirmed = reported - max(settings.QTY_TOLERANCE_MIN_UNITS + 5,
                               int(reported * settings.QTY_TOLERANCE_PCT / 100) + 5)
    from app.models import Dispute, DisputeStatus

    tol = max(settings.QTY_TOLERANCE_MIN_UNITS, reported * settings.QTY_TOLERANCE_PCT / 100)
    pk.quantity_confirmed = confirmed
    pk.photo_url = "mock://uploads/pickup-E.jpg"
    pk.status = PickupStatus.DISPUTED.value
    pk.confirmed_at = utcnow()
    d = Dispute(pickup_id=pk.id, batch_id=E.id, reported_qty=reported, confirmed_qty=confirmed,
                tolerance_units=tol, status=DisputeStatus.OPEN.value)
    db.add(d)
    db.flush()
    batch_state.transition(db, E, BatchState.DISPUTED, actor=dist, event_type="DISPUTE_RAISED",
                           payload={"dispute_id": d.id, "reported_qty": reported, "confirmed_qty": confirmed})
    db.commit()
    steps.append({"step": "Distributor confirms mismatched quantity",
                  "result": f"reported={reported}, confirmed={confirmed}, tolerance={round(tol,1)} "
                            f"-> DISPUTED, batch blocked"})
    return {"scenario": "dispute", "elapsed_seconds": round(time.perf_counter() - t0, 2),
            "dispute_id": d.id, "batch_state": E.state, "steps": steps}


# batches the scripted demos rely on being in a fixed state — pulse leaves them alone
_PROTECTED = {"AZ-2025-D", "AZ-2025-E"}


def run_pulse(db: Session) -> dict:
    """One small burst of realistic network activity — a couple of sales and one batch
    advancing a step — so the dashboard visibly moves during a live demo."""
    import random

    from app.models import PickupRoute

    steps: list[str] = []

    # 1) a sale or two at retailers who still hold ACTIVE stock
    holdings = db.execute(
        select(BatchHolding, Batch)
        .join(Batch, Batch.id == BatchHolding.batch_id)
        .where(BatchHolding.quantity_on_hand > 3, Batch.state == BatchState.ACTIVE.value)
    ).all()
    random.shuffle(holdings)
    for h, b in holdings[:2]:
        qty = random.randint(1, min(4, h.quantity_on_hand))
        retailer = db.get(User, h.retailer_id)
        h.quantity_on_hand -= qty
        db.add(h)
        db.add(PosTransaction(batch_id=b.id, retailer_id=h.retailer_id, quantity=qty, scanned_at=utcnow()))
        registry.record_event(db, event_type="POS_SALE", batch=b, actor=retailer,
                              payload={"quantity": qty, "retailer": retailer.name,
                                       "remaining_on_hand": h.quantity_on_hand})
        db.commit()
        steps.append(f"{retailer.name} sold {qty} × {b.batch_number} ({h.quantity_on_hand} left)")

    # 2) advance one non-protected batch by a single step
    advanced = None
    batches = db.execute(select(Batch).where(Batch.batch_number.notin_(_PROTECTED))).scalars().all()
    random.shuffle(batches)
    for b in batches:
        rr = db.execute(select(ReturnRequest).where(ReturnRequest.batch_id == b.id)).scalars().first()
        if b.state == BatchState.RETURN_INITIATED.value and rr and rr.quantity_reported:
            dist = db.get(User, rr.distributor_id)
            route = PickupRoute(distributor_id=dist.id, algorithm="ortools_cvrp", stops=[], vehicle_capacity=500)
            db.add(route)
            db.flush()
            db.add(Pickup(return_request_id=rr.id, distributor_id=dist.id, route_id=route.id,
                          status=PickupStatus.SCHEDULED.value))
            rr.status = ReturnStatus.PICKUP_SCHEDULED.value
            db.flush()
            batch_state.transition(db, b, BatchState.PICKUP_SCHEDULED, actor=dist,
                                   event_type="PICKUP_SCHEDULED", payload={"return_request_id": rr.id, "trigger": "pulse"})
            advanced = f"{b.batch_number} → PICKUP_SCHEDULED"
        elif b.state == BatchState.PICKUP_SCHEDULED.value:
            pk = db.execute(
                select(Pickup).join(ReturnRequest, ReturnRequest.id == Pickup.return_request_id)
                .where(ReturnRequest.batch_id == b.id, Pickup.status == PickupStatus.SCHEDULED.value)
            ).scalars().first()
            if not pk or not rr or not rr.quantity_reported:
                continue
            dist = db.get(User, pk.distributor_id)
            pk.quantity_confirmed = rr.quantity_reported
            pk.status = PickupStatus.CONFIRMED.value
            pk.confirmed_at = utcnow()
            rr.status = ReturnStatus.PICKED_UP.value
            db.flush()
            batch_state.transition(db, b, BatchState.PICKUP_CONFIRMED, actor=dist,
                                   event_type="PICKUP_CONFIRMED",
                                   payload={"pickup_id": pk.id, "quantity_confirmed": pk.quantity_confirmed,
                                            "within_tolerance": True, "trigger": "pulse"})
            advanced = f"{b.batch_number} → PICKUP_CONFIRMED"
        elif b.state == BatchState.PICKUP_CONFIRMED.value:
            mfr = db.get(User, b.manufacturer_id)
            pk = db.execute(
                select(Pickup).join(ReturnRequest, ReturnRequest.id == Pickup.return_request_id)
                .where(ReturnRequest.batch_id == b.id)
            ).scalars().first()
            qty = (pk.quantity_confirmed if pk else None) or (rr.quantity_reported if rr else 0) or 1
            db.add(ManufacturerReceipt(batch_id=b.id, distributor_id=rr.distributor_id if rr else mfr.id,
                                       manufacturer_id=mfr.id, quantity=qty))
            db.flush()
            batch_state.transition(db, b, BatchState.RECEIVED_BY_MANUFACTURER, actor=mfr,
                                   event_type="RECEIVED_BY_MANUFACTURER", payload={"quantity": qty, "trigger": "pulse"})
            advanced = f"{b.batch_number} → RECEIVED_BY_MANUFACTURER"
        if advanced:
            db.commit()
            steps.append(advanced)
            break

    if not steps:
        steps.append("network is quiet — nothing to simulate (try a demo reset)")
    return {"scenario": "pulse", "steps": steps}
