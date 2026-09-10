from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUser, DbDep, require_roles
from app.models import (
    Batch,
    BatchHolding,
    BatchState,
    PosTransaction,
    ReturnRequest,
    ReturnStatus,
    Role,
    utcnow,
)
from app.schemas import ReturnConfirmIn, SaleIn
from app.services import batch_state, reentry, registry

router = APIRouter(prefix="/retailer", tags=["retailer"])
retailer_only = Depends(require_roles(Role.RETAILER))


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


@router.get("/batches")
def my_batches(user: CurrentUser, db: DbDep, _=retailer_only):
    rows = db.execute(
        select(BatchHolding, Batch)
        .join(Batch, Batch.id == BatchHolding.batch_id)
        .where(BatchHolding.retailer_id == user.id)
    ).all()
    now = utcnow()
    out = []
    for h, b in rows:
        days = (_aware(b.expiry_date).date() - now.date()).days
        out.append(
            {
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "drug_name": b.drug_name,
                "category": b.category,
                "manufacturer_license_id": b.manufacturer_license_id,
                "expiry_date": b.expiry_date,
                "days_to_expiry": days,
                "quantity_on_hand": h.quantity_on_hand,
                "state": b.state,
                "non_compliant": b.non_compliant,
                "reentry_flagged": b.reentry_flagged,
                "expiry_alert_sent": h.expiry_alert_sent,
                "qr_payload": b.qr_payload,
            }
        )
    return out


def _resolve_batch(db, body: SaleIn) -> Batch:
    if body.qr_payload:
        b = db.execute(select(Batch).where(Batch.qr_payload == body.qr_payload)).scalars().first()
    elif body.batch_number and body.manufacturer_license_id:
        b = db.execute(
            select(Batch).where(
                Batch.batch_number == body.batch_number,
                Batch.manufacturer_license_id == body.manufacturer_license_id,
            )
        ).scalars().first()
    else:
        raise HTTPException(422, "Provide qr_payload or (batch_number + manufacturer_license_id)")
    if not b:
        raise HTTPException(404, "Batch not found for scanned code")
    return b


@router.post("/pos/sale", status_code=status.HTTP_201_CREATED)
def pos_sale(body: SaleIn, user: CurrentUser, db: DbDep, _=retailer_only):
    batch = _resolve_batch(db, body)
    # lock the batch + holding rows for the duration of this sale
    batch = db.execute(select(Batch).where(Batch.id == batch.id).with_for_update()).scalars().one()
    holding = db.execute(
        select(BatchHolding)
        .where(BatchHolding.batch_id == batch.id, BatchHolding.retailer_id == user.id)
        .with_for_update()
    ).scalars().first()

    txn = PosTransaction(
        batch_id=batch.id, retailer_id=user.id, quantity=body.quantity, scanned_at=utcnow()
    )
    db.add(txn)
    db.flush()

    alert = reentry.check_and_handle(
        db, batch=batch, retailer=user, quantity=body.quantity, pos_txn=txn
    )
    if alert is not None:
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "status": "BLOCKED_REENTRY",
                "message": f"Sale blocked: batch {batch.batch_number} is in the return pipeline "
                f"({batch.state}). Re-entry alert raised.",
                "alert_id": alert.id,
                "batch_number": batch.batch_number,
                "batch_state": batch.state,
                "attempted_location": user.location_name,
                "notified": {
                    "state_drug_controller": alert.notified_controller,
                    "manufacturer": alert.notified_manufacturer,
                },
                "latency_ms": alert.notification_latency_ms,
            },
        )

    if BatchState(batch.state) != BatchState.ACTIVE:
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Batch {batch.batch_number} is not sellable ({batch.state})")

    if holding is None:
        db.rollback()
        raise HTTPException(400, "You do not hold this batch")

    # Atomic conditional decrement — portable guard against lost updates / negative stock.
    from sqlalchemy import update

    res = db.execute(
        update(BatchHolding)
        .where(
            BatchHolding.id == holding.id,
            BatchHolding.quantity_on_hand >= body.quantity,
        )
        .values(quantity_on_hand=BatchHolding.quantity_on_hand - body.quantity, last_updated=utcnow())
    )
    if res.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Insufficient stock on hand for this batch")

    db.refresh(holding)
    remaining = holding.quantity_on_hand
    registry.record_event(
        db, event_type="POS_SALE", batch=batch, actor=user,
        payload={"quantity": body.quantity, "retailer": user.name, "remaining_on_hand": remaining},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Concurrent sale — stock changed, retry")
    return {
        "status": "SOLD",
        "batch_number": batch.batch_number,
        "quantity": body.quantity,
        "remaining_on_hand": remaining,
        "pos_transaction_id": txn.id,
    }


@router.post("/batches/{batch_id}/initiate-return", status_code=status.HTTP_201_CREATED)
def initiate_return(batch_id: str, body: ReturnConfirmIn, user: CurrentUser, db: DbDep, _=retailer_only):
    """Manual return initiation (fraud demo Batch D). Blocks duplicates (TC-18)."""
    holding = db.execute(
        select(BatchHolding).where(
            BatchHolding.batch_id == batch_id, BatchHolding.retailer_id == user.id
        )
    ).scalars().first()
    if holding is None:
        raise HTTPException(404, "You do not hold this batch")
    batch = db.execute(select(Batch).where(Batch.id == batch_id).with_for_update()).scalars().one()

    existing = db.execute(
        select(ReturnRequest).where(
            ReturnRequest.batch_id == batch_id,
            ReturnRequest.retailer_id == user.id,
            ReturnRequest.status != ReturnStatus.CLOSED.value,
        )
    ).scalars().first()
    if existing and existing.status != ReturnStatus.AUTO_CREATED.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "A return request for this batch is already open",
                    "existing_return_id": existing.id, "status": existing.status},
        )

    rr = existing or ReturnRequest(
        batch_id=batch_id, retailer_id=user.id,
        distributor_id=user.mapped_distributor_id, expiry_date=batch.expiry_date,
    )
    rr.quantity_reported = body.quantity_reported
    rr.condition = body.condition
    rr.photo_url = body.photo_url or "mock://uploads/return-condition.jpg"
    rr.status = ReturnStatus.RETURN_INITIATED.value
    rr.confirmed_at = utcnow()
    db.add(rr)
    db.flush()

    if BatchState(batch.state) == BatchState.ACTIVE:
        batch_state.transition(
            db, batch, BatchState.RETURN_INITIATED, actor=user, event_type="RETURN_INITIATED",
            payload={"return_request_id": rr.id, "quantity_reported": body.quantity_reported,
                     "condition": body.condition, "trigger": "manual"},
        )
    else:
        registry.record_event(
            db, event_type="RETURN_CONFIRMED", batch=batch, actor=user,
            payload={"return_request_id": rr.id, "quantity_reported": body.quantity_reported},
        )
    db.commit()
    return {"status": "RETURN_INITIATED", "return_id": rr.id, "batch_number": batch.batch_number,
            "batch_state": batch.state, "flagged": True, "flagged_at": batch.flagged_at}


@router.get("/returns")
def my_returns(user: CurrentUser, db: DbDep, _=retailer_only):
    rrs = db.execute(
        select(ReturnRequest, Batch)
        .join(Batch, Batch.id == ReturnRequest.batch_id)
        .where(ReturnRequest.retailer_id == user.id)
        .order_by(ReturnRequest.created_at.desc())
    ).all()
    return [
        {
            "id": rr.id,
            "batch_id": rr.batch_id,
            "batch_number": b.batch_number,
            "drug_name": b.drug_name,
            "status": rr.status,
            "quantity_reported": rr.quantity_reported,
            "condition": rr.condition,
            "photo_url": rr.photo_url,
            "created_at": rr.created_at,
            "batch_state": b.state,
        }
        for rr, b in rrs
    ]


@router.post("/returns/{return_id}/confirm")
def confirm_return(return_id: str, body: ReturnConfirmIn, user: CurrentUser, db: DbDep, _=retailer_only):
    rr = db.get(ReturnRequest, return_id)
    if not rr or rr.retailer_id != user.id:
        raise HTTPException(404, "Return request not found")
    if rr.status not in (ReturnStatus.AUTO_CREATED.value, ReturnStatus.RETURN_INITIATED.value):
        raise HTTPException(409, f"Return already progressed ({rr.status})")
    batch = db.get(Batch, rr.batch_id)

    rr.quantity_reported = body.quantity_reported
    rr.condition = body.condition
    rr.photo_url = body.photo_url or "mock://uploads/return-condition.jpg"
    rr.status = ReturnStatus.RETURN_INITIATED.value
    rr.confirmed_at = utcnow()
    db.add(rr)

    registry.record_event(
        db, event_type="RETURN_CONFIRMED", batch=batch, actor=user,
        payload={"return_request_id": rr.id, "quantity_reported": body.quantity_reported,
                 "condition": body.condition, "photo_url": rr.photo_url},
    )
    db.commit()
    return {"status": "RETURN_INITIATED", "return_id": rr.id, "batch_number": batch.batch_number,
            "batch_state": batch.state, "flagged": True}
