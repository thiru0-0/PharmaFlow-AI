from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep, require_roles
from app.models import (
    Batch,
    BatchState,
    DestructionCertificate,
    ManufacturerReceipt,
    Pickup,
    PickupStatus,
    ReturnRequest,
    Role,
    User,
    utcnow,
)
from app.schemas import CertificateIn, ReceiptIn
from app.services import batch_state, notifications, registry

router = APIRouter(prefix="/manufacturer", tags=["manufacturer"])
mfr_only = Depends(require_roles(Role.MANUFACTURER))

CERT_BLOCKED_MSG = "Certificate upload blocked: confirmed manufacturer receipt not found for this batch."


@router.get("/inbound")
def inbound(user: CurrentUser, db: DbDep, _=mfr_only):
    """Confirmed pickups for this manufacturer's batches, awaiting a receipt."""
    rows = db.execute(
        select(Batch, Pickup, ReturnRequest)
        .join(ReturnRequest, ReturnRequest.batch_id == Batch.id)
        .join(Pickup, Pickup.return_request_id == ReturnRequest.id)
        .where(
            Batch.manufacturer_id == user.id,
            Pickup.status.in_([PickupStatus.CONFIRMED.value, PickupStatus.RESOLVED.value]),
            Batch.state == BatchState.PICKUP_CONFIRMED.value,
        )
    ).all()
    return [
        {"batch_id": b.id, "batch_number": b.batch_number, "drug_name": b.drug_name,
         "quantity_confirmed": p.quantity_confirmed, "batch_state": b.state}
        for b, p, rr in rows
    ]


@router.post("/receipts", status_code=status.HTTP_201_CREATED)
def create_receipt(body: ReceiptIn, user: CurrentUser, db: DbDep, _=mfr_only):
    batch = db.execute(select(Batch).where(Batch.id == body.batch_id).with_for_update()).scalars().first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    if batch.manufacturer_id != user.id:
        raise HTTPException(403, "Not your batch")
    if BatchState(batch.state) != BatchState.PICKUP_CONFIRMED:
        raise HTTPException(409, f"Batch not ready for receipt (state {batch.state})")
    if db.execute(select(ManufacturerReceipt).where(ManufacturerReceipt.batch_id == batch.id)).scalars().first():
        raise HTTPException(409, "Receipt already recorded for this batch")

    rr = db.execute(select(ReturnRequest).where(ReturnRequest.batch_id == batch.id)).scalars().first()
    receipt = ManufacturerReceipt(
        batch_id=batch.id, distributor_id=rr.distributor_id if rr else user.id,
        manufacturer_id=user.id, quantity=body.quantity,
    )
    db.add(receipt)
    db.flush()
    batch_state.transition(
        db, batch, BatchState.RECEIVED_BY_MANUFACTURER, actor=user, event_type="RECEIVED_BY_MANUFACTURER",
        payload={"receipt_id": receipt.id, "quantity": body.quantity},
    )
    db.commit()
    return {"status": "RECEIVED_BY_MANUFACTURER", "receipt_id": receipt.id, "batch_state": batch.state}


@router.get("/receipts")
def list_receipts(user: CurrentUser, db: DbDep, _=mfr_only):
    rows = db.execute(
        select(ManufacturerReceipt, Batch)
        .join(Batch, Batch.id == ManufacturerReceipt.batch_id)
        .where(ManufacturerReceipt.manufacturer_id == user.id)
        .order_by(ManufacturerReceipt.received_at.desc())
    ).all()
    out = []
    for rc, b in rows:
        cert = db.execute(
            select(DestructionCertificate).where(DestructionCertificate.batch_id == b.id)
        ).scalars().first()
        out.append({
            "receipt_id": rc.id, "batch_id": b.id, "batch_number": b.batch_number,
            "drug_name": b.drug_name, "quantity": rc.quantity, "received_at": rc.received_at,
            "batch_state": b.state, "certificate_id": cert.id if cert else None,
        })
    return out


@router.post("/certificates", status_code=status.HTTP_201_CREATED)
def upload_certificate(body: CertificateIn, user: CurrentUser, db: DbDep, _=mfr_only):
    batch = db.execute(select(Batch).where(Batch.id == body.batch_id).with_for_update()).scalars().first()
    if not batch:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Rejected as invalid: batch not found in the registry")
    if batch.manufacturer_id != user.id:
        raise HTTPException(403, "Not your batch")

    receipt = db.execute(
        select(ManufacturerReceipt).where(ManufacturerReceipt.batch_id == batch.id)
    ).scalars().first()
    if receipt is None:
        raise HTTPException(status.HTTP_409_CONFLICT, CERT_BLOCKED_MSG)
    if BatchState(batch.state) != BatchState.RECEIVED_BY_MANUFACTURER:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Batch must be RECEIVED_BY_MANUFACTURER before a certificate ({batch.state})")
    if db.execute(select(DestructionCertificate).where(DestructionCertificate.batch_id == batch.id)).scalars().first():
        raise HTTPException(409, "Certificate already issued for this batch")

    cert = DestructionCertificate(
        batch_id=batch.id, receipt_id=receipt.id, manufacturer_id=user.id,
        facility_name=body.facility_name, cert_url=body.cert_url, reason=body.reason,
    )
    db.add(cert)
    db.flush()
    batch_state.transition(
        db, batch, BatchState.DESTROYED_CERTIFIED, actor=user, event_type="DESTROYED_CERTIFIED",
        payload={"certificate_id": cert.id, "facility": body.facility_name, "reason": body.reason,
                 "cert_url": body.cert_url},
    )
    # auto disposal record
    disposal = {
        "drug_name": batch.drug_name, "batch_number": batch.batch_number,
        "expiry_date": str(batch.expiry_date), "reason_for_disposal": body.reason,
        "certificate_reference": cert.id,
    }
    rr = db.execute(select(ReturnRequest).where(ReturnRequest.batch_id == batch.id)).scalars().first()
    if rr:
        notifications.notify(db, recipient=db.get(User, rr.retailer_id), recipient_label="RETAILER",
                             type_="CERTIFICATE_ISSUED", payload=disposal, channels=["in_app"], batch_id=batch.id)
        notifications.notify(db, recipient=db.get(User, rr.distributor_id), recipient_label="DISTRIBUTOR",
                             type_="CERTIFICATE_ISSUED", payload=disposal, channels=["in_app"], batch_id=batch.id)
    db.commit()
    return {"status": "DESTROYED_CERTIFIED", "certificate_id": cert.id, "batch_state": batch.state,
            "disposal_record": disposal}
