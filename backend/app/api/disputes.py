from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep
from app.models import (
    Batch,
    BatchState,
    Dispute,
    DisputeEvidence,
    DisputeStatus,
    Pickup,
    PickupStatus,
    ReturnRequest,
    ReturnStatus,
    Role,
    User,
    utcnow,
)
from app.schemas import EvidenceIn, ResolveDisputeIn
from app.services import batch_state, notifications, registry

router = APIRouter(prefix="/disputes", tags=["disputes"])


def _dispute_view(db, d: Dispute) -> dict:
    pickup = db.get(Pickup, d.pickup_id)
    rr = db.get(ReturnRequest, pickup.return_request_id)
    batch = db.get(Batch, d.batch_id)
    retailer = db.get(User, rr.retailer_id)
    distributor = db.get(User, pickup.distributor_id)
    evidence = db.execute(
        select(DisputeEvidence).where(DisputeEvidence.dispute_id == d.id).order_by(DisputeEvidence.created_at)
    ).scalars().all()
    return {
        "id": d.id,
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "batch_state": batch.state,
        "retailer": retailer.name,
        "distributor": distributor.name,
        "reported_qty": d.reported_qty,
        "confirmed_qty": d.confirmed_qty,
        "difference": abs(d.reported_qty - d.confirmed_qty),
        "tolerance_units": round(d.tolerance_units, 2),
        "status": d.status,
        "reconciled_qty": d.reconciled_qty,
        "resolution_notes": d.resolution_notes,
        "retailer_photo": rr.photo_url,
        "distributor_photo": pickup.photo_url,
        "created_at": d.created_at,
        "resolved_at": d.resolved_at,
        "evidence": [
            {"by": db.get(User, e.submitted_by).name, "note": e.note, "file_url": e.file_url,
             "at": e.created_at}
            for e in evidence
        ],
    }


@router.get("")
def list_disputes(user: CurrentUser, db: DbDep):
    q = select(Dispute).order_by(Dispute.created_at.desc())
    disputes = db.execute(q).scalars().all()
    views = [_dispute_view(db, d) for d in disputes]
    if user.role in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        return views
    # entity roles see only their own
    out = []
    for d, v in zip(disputes, views):
        pickup = db.get(Pickup, d.pickup_id)
        rr = db.get(ReturnRequest, pickup.return_request_id)
        if user.id in (rr.retailer_id, pickup.distributor_id):
            out.append(v)
    return out


@router.get("/{dispute_id}")
def get_dispute(dispute_id: str, user: CurrentUser, db: DbDep):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "Dispute not found")
    return _dispute_view(db, d)


@router.post("/{dispute_id}/evidence")
def submit_evidence(dispute_id: str, body: EvidenceIn, user: CurrentUser, db: DbDep):
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "Dispute not found")
    if d.status != DisputeStatus.OPEN.value:
        raise HTTPException(409, "Dispute is already resolved")
    pickup = db.get(Pickup, d.pickup_id)
    rr = db.get(ReturnRequest, pickup.return_request_id)
    if user.role not in (Role.ADMIN.value,) and user.id not in (rr.retailer_id, pickup.distributor_id):
        raise HTTPException(403, "Not a party to this dispute")
    ev = DisputeEvidence(dispute_id=d.id, submitted_by=user.id, note=body.note,
                         file_url=body.file_url or "mock://uploads/dispute-evidence.jpg")
    db.add(ev)
    batch = db.get(Batch, d.batch_id)
    registry.record_event(db, event_type="DISPUTE_EVIDENCE", batch=batch, actor=user,
                          payload={"dispute_id": d.id, "note": body.note})
    db.commit()
    return {"status": "EVIDENCE_ADDED", "dispute_id": d.id}


@router.post("/{dispute_id}/resolve")
def resolve_dispute(dispute_id: str, body: ResolveDisputeIn, user: CurrentUser, db: DbDep):
    """Only a distributor supervisor / platform admin adjudicates."""
    if user.role not in (Role.ADMIN.value,):
        raise HTTPException(403, "Only a platform admin / supervisor can adjudicate a dispute")
    d = db.get(Dispute, dispute_id)
    if not d:
        raise HTTPException(404, "Dispute not found")
    if d.status != DisputeStatus.OPEN.value:
        raise HTTPException(409, "Dispute already resolved")

    pickup = db.execute(select(Pickup).where(Pickup.id == d.pickup_id).with_for_update()).scalars().one()
    rr = db.get(ReturnRequest, pickup.return_request_id)
    batch = db.execute(select(Batch).where(Batch.id == d.batch_id).with_for_update()).scalars().one()

    d.status = DisputeStatus.RESOLVED.value
    d.reconciled_qty = body.reconciled_qty
    d.resolution_notes = body.resolution_notes
    d.resolved_by = user.id
    d.resolved_at = utcnow()
    db.add(d)

    pickup.status = PickupStatus.RESOLVED.value
    pickup.quantity_confirmed = body.reconciled_qty
    rr.status = ReturnStatus.PICKED_UP.value
    db.add_all([pickup, rr])

    batch_state.transition(
        db, batch, BatchState.PICKUP_CONFIRMED, actor=user, event_type="DISPUTE_RESOLVED",
        payload={"dispute_id": d.id, "reconciled_qty": body.reconciled_qty,
                 "resolution_notes": body.resolution_notes},
    )
    p = {"batch_number": batch.batch_number, "reconciled_qty": body.reconciled_qty, "dispute_id": d.id}
    notifications.notify(db, recipient=db.get(User, rr.retailer_id), recipient_label="RETAILER",
                         type_="DISPUTE_RESOLVED", payload=p, channels=["in_app"], batch_id=batch.id)
    notifications.notify(db, recipient=db.get(User, pickup.distributor_id), recipient_label="DISTRIBUTOR",
                         type_="DISPUTE_RESOLVED", payload=p, channels=["in_app"], batch_id=batch.id)
    db.commit()
    return {"status": "RESOLVED", "batch_state": batch.state, "reconciled_qty": body.reconciled_qty}
