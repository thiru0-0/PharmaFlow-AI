from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbDep
from app.models import (
    Batch,
    BatchState,
    DestructionCertificate,
    Dispute,
    DisputeStatus,
    ManufacturerReceipt,
    Notification,
    ReentryAlert,
    RegistryEvent,
    ReturnRequest,
    Role,
    User,
)
from app.services import registry as reg

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _batch_scope(db, user: User) -> set[str] | None:
    if user.role in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        return None
    from app.models import BatchHolding

    if user.role == Role.MANUFACTURER.value:
        return set(db.execute(select(Batch.id).where(Batch.manufacturer_id == user.id)).scalars().all())
    if user.role == Role.RETAILER.value:
        return set(db.execute(select(BatchHolding.batch_id).where(BatchHolding.retailer_id == user.id)).scalars().all())
    if user.role == Role.DISTRIBUTOR.value:
        return set(db.execute(select(ReturnRequest.batch_id).where(ReturnRequest.distributor_id == user.id)).scalars().all())
    return set()


@router.get("/summary")
def summary(user: CurrentUser, db: DbDep):
    scope = _batch_scope(db, user)
    batches = db.execute(select(Batch)).scalars().all()
    if scope is not None:
        batches = [b for b in batches if b.id in scope]

    funnel = {s.value: 0 for s in BatchState}
    non_compliant = 0
    reentry_flagged = 0
    for b in batches:
        funnel[b.state] += 1
        non_compliant += int(b.non_compliant)
        reentry_flagged += int(b.reentry_flagged)

    open_disputes = db.execute(
        select(Dispute).where(Dispute.status == DisputeStatus.OPEN.value)
    ).scalars().all()
    alerts = db.execute(select(ReentryAlert).order_by(ReentryAlert.triggered_at.desc())).scalars().all()
    if scope is not None:
        open_disputes = [d for d in open_disputes if d.batch_id in scope]
        alerts = [a for a in alerts if a.batch_id in scope]

    health = reg.verify_all(db, use_cache=True) if user.role in (Role.ADMIN.value, Role.STATE_DRUG_CONTROLLER.value) else None
    total_terminal = funnel[BatchState.DESTROYED_CERTIFIED.value]
    total = len(batches) or 1

    return {
        "funnel": funnel,
        "totals": {
            "batches": len(batches),
            "in_return_pipeline": sum(
                funnel[s] for s in (
                    BatchState.RETURN_INITIATED.value, BatchState.PICKUP_SCHEDULED.value,
                    BatchState.DISPUTED.value, BatchState.PICKUP_CONFIRMED.value,
                    BatchState.RECEIVED_BY_MANUFACTURER.value,
                )
            ),
            "destroyed_certified": total_terminal,
            "non_compliant": non_compliant,
            "reentry_flagged": reentry_flagged,
        },
        "compliance_rate": round(1 - non_compliant / total, 3),
        "open_disputes": [
            {"id": d.id, "batch_id": d.batch_id, "reported_qty": d.reported_qty,
             "confirmed_qty": d.confirmed_qty, "created_at": d.created_at}
            for d in open_disputes
        ],
        "reentry_alerts": [
            {"id": a.id, "batch_number": a.batch_number, "status": a.status,
             "attempted_retailer": a.attempted_retailer_name,
             "notification_latency_ms": a.notification_latency_ms,
             "notified_controller": a.notified_controller,
             "notified_manufacturer": a.notified_manufacturer,
             "triggered_at": a.triggered_at}
            for a in alerts
        ],
        "registry_health": health,
    }


@router.get("/events/stream")
def events_stream(user: CurrentUser, db: DbDep, since_id: int = 0, limit: int = 50):
    """Short-poll live feed. Pass since_id to get only newer events."""
    scope = _batch_scope(db, user)
    q = select(RegistryEvent).where(RegistryEvent.id > since_id).order_by(RegistryEvent.id.asc()).limit(limit)
    rows = db.execute(q).scalars().all()
    out = []
    for e in rows:
        if scope is not None and e.batch_id not in scope:
            continue
        out.append({
            "id": e.id, "seq": e.seq, "event_type": e.event_type, "actor": e.actor_name,
            "batch_number": e.batch_number, "hash": e.hash, "created_at": e.created_at,
            "payload": e.payload,
        })
    last_id = rows[-1].id if rows else since_id
    return {"events": out, "last_id": last_id}


@router.get("/directory")
def directory(user: CurrentUser, db: DbDep):
    from sqlalchemy.orm import joinedload

    users = db.execute(select(User).options(joinedload(User.license))).scalars().all()
    return [
        {
            "id": u.id, "name": u.name, "role": u.role, "location": u.location_name,
            "license": u.license.license_number if u.license else None,
            "license_status": u.license.status if u.license else None,
            "mapped_distributor_id": u.mapped_distributor_id,
            "mapped_manufacturer_id": u.mapped_manufacturer_id,
        }
        for u in users
    ]


@router.get("/batches")
def all_batches(user: CurrentUser, db: DbDep):
    scope = _batch_scope(db, user)
    batches = db.execute(select(Batch).order_by(Batch.batch_number)).scalars().all()
    out = []
    for b in batches:
        if scope is not None and b.id not in scope:
            continue
        out.append({
            "batch_id": b.id, "batch_number": b.batch_number, "drug_name": b.drug_name,
            "manufacturer_license_id": b.manufacturer_license_id, "category": b.category,
            "expiry_date": b.expiry_date, "state": b.state, "non_compliant": b.non_compliant,
            "reentry_flagged": b.reentry_flagged, "flagged_at": b.flagged_at,
        })
    return out


@router.get("/batches/{batch_id}/timeline")
def batch_timeline(batch_id: str, user: CurrentUser, db: DbDep):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    scope = _batch_scope(db, user)
    if scope is not None and batch.id not in scope:
        raise HTTPException(403, "Not permitted")
    events = db.execute(
        select(RegistryEvent).where(RegistryEvent.batch_id == batch_id).order_by(RegistryEvent.seq)
    ).scalars().all()
    rr = db.execute(select(ReturnRequest).where(ReturnRequest.batch_id == batch_id)).scalars().first()
    receipt = db.execute(select(ManufacturerReceipt).where(ManufacturerReceipt.batch_id == batch_id)).scalars().first()
    cert = db.execute(select(DestructionCertificate).where(DestructionCertificate.batch_id == batch_id)).scalars().first()
    dispute = db.execute(select(Dispute).where(Dispute.batch_id == batch_id)).scalars().first()
    alerts = db.execute(select(ReentryAlert).where(ReentryAlert.batch_id == batch_id)).scalars().all()
    verification = reg.verify_batch_chain(db, batch)
    return {
        "batch": {
            "id": batch.id, "batch_number": batch.batch_number, "drug_name": batch.drug_name,
            "manufacturer_license_id": batch.manufacturer_license_id, "category": batch.category,
            "mfg_date": batch.mfg_date, "expiry_date": batch.expiry_date, "state": batch.state,
            "non_compliant": batch.non_compliant, "reentry_flagged": batch.reentry_flagged,
            "flagged_at": batch.flagged_at,
        },
        "verification": verification,
        "return_request": None if not rr else {
            "id": rr.id, "status": rr.status, "quantity_reported": rr.quantity_reported,
            "condition": rr.condition, "photo_url": rr.photo_url, "created_at": rr.created_at,
        },
        "receipt": None if not receipt else {
            "id": receipt.id, "quantity": receipt.quantity, "received_at": receipt.received_at,
        },
        "certificate": None if not cert else {
            "id": cert.id, "facility": cert.facility_name, "reason": cert.reason,
            "cert_url": cert.cert_url, "issued_at": cert.issued_at,
        },
        "dispute": None if not dispute else {
            "id": dispute.id, "status": dispute.status, "reported_qty": dispute.reported_qty,
            "confirmed_qty": dispute.confirmed_qty, "reconciled_qty": dispute.reconciled_qty,
        },
        "reentry_alerts": [
            {"id": a.id, "status": a.status, "attempted_retailer": a.attempted_retailer_name,
             "attempted_location": a.attempted_location, "triggered_at": a.triggered_at}
            for a in alerts
        ],
        "timeline": [
            {"seq": e.seq, "event_type": e.event_type, "actor": e.actor_name,
             "payload": e.payload, "hash": e.hash, "created_at": e.created_at}
            for e in events
        ],
    }


@router.get("/notifications")
def my_notifications(user: CurrentUser, db: DbDep, limit: int = 50):
    q = (
        select(Notification)
        .where((Notification.recipient_id == user.id) | (Notification.recipient_label.like(f"{user.role}%")))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(q).scalars().all()
    return [
        {"id": n.id, "type": n.type, "channel": n.channel, "delivery_status": n.delivery_status,
         "payload": n.payload, "read": n.read, "created_at": n.created_at, "recipient": n.recipient_label}
        for n in rows
    ]


@router.get("/compliance-export.csv")
def compliance_export(user: CurrentUser, db: DbDep):
    if user.role not in (Role.ADMIN.value, Role.STATE_DRUG_CONTROLLER.value):
        raise HTTPException(403, "Regulator/admin only")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "drug_name", "batch_number", "expiry_date", "reason_for_disposal", "retailer",
        "distributor", "manufacturer", "return_initiated_at", "pickup_confirmed_at",
        "received_at", "certificate_issued_at", "status", "certificate_reference",
    ])
    batches = db.execute(select(Batch)).scalars().all()
    for b in batches:
        rr = db.execute(select(ReturnRequest).where(ReturnRequest.batch_id == b.id)).scalars().first()
        receipt = db.execute(select(ManufacturerReceipt).where(ManufacturerReceipt.batch_id == b.id)).scalars().first()
        cert = db.execute(select(DestructionCertificate).where(DestructionCertificate.batch_id == b.id)).scalars().first()
        retailer = db.get(User, rr.retailer_id) if rr else None
        distributor = db.get(User, rr.distributor_id) if rr else None
        manufacturer = db.get(User, b.manufacturer_id)
        events = {e.event_type: e.created_at for e in db.execute(
            select(RegistryEvent).where(RegistryEvent.batch_id == b.id)).scalars().all()}
        w.writerow([
            b.drug_name, b.batch_number, b.expiry_date,
            cert.reason if cert else ("expired" if rr else ""),
            retailer.name if retailer else "", distributor.name if distributor else "",
            manufacturer.name if manufacturer else "",
            events.get("RETURN_INITIATED") or events.get("RETURN_AUTO_CREATED") or "",
            events.get("PICKUP_CONFIRMED") or "", receipt.received_at if receipt else "",
            cert.issued_at if cert else "", b.state, cert.id if cert else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pharmaflow_compliance_export.csv"},
    )
