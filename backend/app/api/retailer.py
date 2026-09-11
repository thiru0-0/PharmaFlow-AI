from __future__ import annotations

import re
import uuid
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
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


def _deduct_stock(db, holding: BatchHolding, qty: int) -> bool:
    """Atomically remove `qty` units from a holding. False (no-op) if stock is insufficient."""
    res = db.execute(
        update(BatchHolding)
        .where(BatchHolding.id == holding.id, BatchHolding.quantity_on_hand >= qty)
        .values(quantity_on_hand=BatchHolding.quantity_on_hand - qty, last_updated=utcnow())
    )
    return res.rowcount == 1


def _split_qr_payload(parent: Batch, child_batch_number: str, serial: str) -> str:
    """New GS1-style payload for a split-off batch, reusing the parent's GTIN+expiry
    segment but with the split batch's own (10) lot number and (21) serial."""
    m = re.match(r"^(.*?)\(10\)", parent.qr_payload)
    prefix = m.group(1) if m else f"(01)0890123450000(17){parent.expiry_date.strftime('%y%m%d')}"
    return f"{prefix}(10){child_batch_number}(21){serial}"


def _split_batch_for_return(db, *, parent: Batch, qty: int, actor) -> Batch:
    """Split `qty` units off `parent` into a brand-new batch identity that enters the
    return pipeline on its own, so the parent can stay ACTIVE and sellable for whatever
    stock wasn't returned. Mirrors how a real partial recall issues a distinct sub-lot
    instead of pulling an entire batch from sale over a partial return.

    The child gets its own registry hash-chain (genesis event = BATCH_SPLIT_FOR_RETURN,
    linking back to the parent) — from here on it's tracked exactly like any other batch
    by the distributor/manufacturer pages, which key everything off batch_id.
    """
    serial = uuid.uuid4().hex[:8].upper()
    child_number = f"{parent.batch_number}-RET-{serial[:6]}"
    child = Batch(
        drug_name=parent.drug_name,
        batch_number=child_number,
        manufacturer_license_id=parent.manufacturer_license_id,
        manufacturer_id=parent.manufacturer_id,
        mfg_date=parent.mfg_date,
        expiry_date=parent.expiry_date,
        category=parent.category,
        qr_payload=_split_qr_payload(parent, child_number, serial),
    )
    db.add(child)
    db.flush()
    registry.record_event(
        db, event_type="BATCH_SPLIT_FOR_RETURN", batch=child, actor=actor,
        payload={"parent_batch_id": parent.id, "parent_batch_number": parent.batch_number,
                 "quantity_split": qty, "drug_name": parent.drug_name},
    )
    return child


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
    if not _deduct_stock(db, holding, body.quantity):
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

    # Snapshot on-hand *before* deduction — this decides whether the whole batch is
    # being retired (full return) or just part of it (partial: split off a new batch
    # identity for the return pipeline so the remainder stays ACTIVE and sellable).
    quantity_before = holding.quantity_on_hand
    is_partial = (
        BatchState(batch.state) == BatchState.ACTIVE
        and existing is None
        and body.quantity_reported < quantity_before
    )

    # First time this return is being counted: pull the reported quantity out of active
    # on-hand stock now — those units are being handed off, not sellable. (existing.status
    # == AUTO_CREATED means it was never confirmed/deducted before; `existing is None`
    # means this is brand new.)
    if not _deduct_stock(db, holding, body.quantity_reported):
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Reported quantity exceeds current stock on hand for this batch")

    if is_partial:
        # Only the returned units leave circulation — the parent batch keeps its
        # remaining stock ACTIVE, unflagged, and sellable under the same QR.
        child = _split_batch_for_return(db, parent=batch, qty=body.quantity_reported, actor=user)
        rr = ReturnRequest(
            batch_id=child.id, retailer_id=user.id,
            distributor_id=user.mapped_distributor_id, expiry_date=child.expiry_date,
            quantity_reported=body.quantity_reported, condition=body.condition,
            photo_url=body.photo_url or "mock://uploads/return-condition.jpg",
            status=ReturnStatus.RETURN_INITIATED.value, confirmed_at=utcnow(),
        )
        db.add(rr)
        db.flush()
        batch_state.transition(
            db, child, BatchState.RETURN_INITIATED, actor=user, event_type="RETURN_INITIATED",
            payload={"return_request_id": rr.id, "quantity_reported": body.quantity_reported,
                     "condition": body.condition, "trigger": "manual_partial_split",
                     "split_from_batch_id": batch.id, "split_from_batch_number": batch.batch_number},
        )
        db.commit()
        db.refresh(holding)
        return {"status": "RETURN_INITIATED", "return_id": rr.id, "batch_number": child.batch_number,
                "batch_state": child.state, "flagged": True, "flagged_at": child.flagged_at,
                "remaining_on_hand": holding.quantity_on_hand,
                "split": True, "original_batch_number": batch.batch_number,
                "original_qr_payload": batch.qr_payload, "return_qr_payload": child.qr_payload}

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
    db.refresh(holding)
    return {"status": "RETURN_INITIATED", "return_id": rr.id, "batch_number": batch.batch_number,
            "batch_state": batch.state, "flagged": True, "flagged_at": batch.flagged_at,
            "remaining_on_hand": holding.quantity_on_hand, "split": False}


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
    rr = db.execute(
        select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
    ).scalars().first()
    if not rr or rr.retailer_id != user.id:
        raise HTTPException(404, "Return request not found")
    if rr.status != ReturnStatus.AUTO_CREATED.value:
        # Already counted once (or further along) — never deduct stock twice.
        raise HTTPException(409, f"Return already confirmed ({rr.status})")
    batch = db.get(Batch, rr.batch_id)

    holding = db.execute(
        select(BatchHolding)
        .where(BatchHolding.batch_id == rr.batch_id, BatchHolding.retailer_id == user.id)
        .with_for_update()
    ).scalars().first()
    if holding is None:
        raise HTTPException(400, "You do not hold this batch")

    if not _deduct_stock(db, holding, body.quantity_reported):
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Reported quantity exceeds current stock on hand for this batch")

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
    db.refresh(holding)
    return {"status": "RETURN_INITIATED", "return_id": rr.id, "batch_number": batch.batch_number,
            "batch_state": batch.state, "flagged": True, "remaining_on_hand": holding.quantity_on_hand}
