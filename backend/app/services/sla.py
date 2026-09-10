from __future__ import annotations

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Batch,
    BatchState,
    DestructionCertificate,
    ManufacturerReceipt,
    Notification,
    ReturnRequest,
    Role,
    utcnow,
)
from app.services import notifications


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def scan(db: Session) -> dict:
    """Detect retailer return-window and manufacturer disposal-window breaches.

    Breach -> batch.non_compliant = True + escalation notification to the regulator.
    """
    now = utcnow()
    breaches = []

    # Retailer return window: measured from expiry date until PICKUP_CONFIRMED reached.
    rrs = db.execute(select(ReturnRequest)).scalars().all()
    for rr in rrs:
        batch = db.get(Batch, rr.batch_id)
        if batch is None:
            continue
        from app.models import STATE_ORDER

        if STATE_ORDER[BatchState(batch.state)] >= STATE_ORDER[BatchState.PICKUP_CONFIRMED]:
            continue
        days = (now - _aware(rr.expiry_date)).days
        if days > settings.RETAILER_RETURN_WINDOW_DAYS and not batch.non_compliant:
            batch.non_compliant = True
            db.add(batch)
            _escalate(db, batch, "RETAILER_RETURN_SLA_BREACH", rr.retailer_id, days)
            breaches.append({"batch": batch.batch_number, "type": "retailer_return", "days": days})

    # Manufacturer disposal window: receipt -> certificate.
    receipts = db.execute(select(ManufacturerReceipt)).scalars().all()
    for rc in receipts:
        cert = db.execute(
            select(DestructionCertificate).where(DestructionCertificate.batch_id == rc.batch_id)
        ).scalars().first()
        end = _aware(cert.issued_at) if cert else now
        days = (end - _aware(rc.received_at)).days
        if days > settings.MANUFACTURER_DISPOSAL_WINDOW_DAYS:
            batch = db.get(Batch, rc.batch_id)
            if batch and not batch.non_compliant:
                batch.non_compliant = True
                db.add(batch)
                _escalate(db, batch, "MANUFACTURER_DISPOSAL_SLA_BREACH", rc.manufacturer_id, days)
                breaches.append({"batch": batch.batch_number, "type": "manufacturer_disposal", "days": days})

    db.commit()
    return {"breaches": breaches, "count": len(breaches)}


def _escalate(db: Session, batch: Batch, kind: str, offender_id: str, days: int) -> None:
    payload = {"batch_number": batch.batch_number, "breach": kind, "days_elapsed": days}
    notifications.notify_role(
        db, Role.STATE_DRUG_CONTROLLER, type_="SLA_BREACH", payload=payload,
        channels=["in_app", "email"], batch_id=batch.id,
    )
    from app.models import User

    off = db.get(User, offender_id)
    if off:
        notifications.notify(
            db, recipient=off, recipient_label=f"{off.role}:{off.name}", type_="SLA_BREACH",
            payload=payload, channels=["in_app", "email"], batch_id=batch.id,
        )
    from app.services import registry

    registry.record_event(db, event_type="SLA_BREACH", batch=batch, actor=None, payload=payload)
