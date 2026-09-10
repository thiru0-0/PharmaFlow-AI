from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Batch,
    BatchState,
    PosTransaction,
    ReentryAlert,
    Role,
    User,
    utcnow,
)
from app.services import notifications, registry


def check_and_handle(
    db: Session, *, batch: Batch, retailer: User, quantity: int, pos_txn: PosTransaction
) -> ReentryAlert | None:
    """Synchronous re-entry check on a POS scan.

    Time-bound: only a scan strictly after batch.flagged_at is suspicious. Returns the
    created alert (sale must be blocked by caller) or None (sale may proceed).
    Target: scan -> both notifications in under REENTRY_TARGET_SECONDS.
    """
    t0 = time.perf_counter()
    if batch.flagged_at is None:
        return None
    scan_time = pos_txn.scanned_at or utcnow()
    flagged_at = batch.flagged_at
    if flagged_at.tzinfo is None:
        flagged_at = flagged_at.replace(tzinfo=timezone.utc)
    if scan_time.tzinfo is None:
        scan_time = scan_time.replace(tzinfo=timezone.utc)
    if scan_time <= flagged_at:
        return None  # legitimate historical sale — never retroactively flagged

    pos_txn.flagged = True
    pos_txn.blocked = True

    manufacturer = db.get(User, batch.manufacturer_id)

    # origin: retailer that initiated the return
    from app.models import ReturnRequest

    rr = (
        db.execute(
            select(ReturnRequest).where(ReturnRequest.batch_id == batch.id).order_by(ReturnRequest.created_at.asc())
        )
        .scalars()
        .first()
    )
    origin_retailer = db.get(User, rr.retailer_id) if rr else None

    alert = ReentryAlert(
        batch_id=batch.id,
        batch_number=batch.batch_number,
        pos_transaction_id=pos_txn.id,
        attempted_retailer_id=retailer.id,
        attempted_retailer_name=retailer.name,
        attempted_location=retailer.location_name,
        origin_location=origin_retailer.location_name if origin_retailer else None,
        attempted_quantity=quantity,
        batch_state_at_attempt=batch.state,
        severity="CRITICAL",
    )
    db.add(alert)

    batch.reentry_flagged = True
    db.add(batch)

    payload = {
        "alert": "RE-ENTRY ATTEMPT BLOCKED",
        "batch_number": batch.batch_number,
        "batch_state": batch.state,
        "attempted_retailer": retailer.name,
        "attempted_location": retailer.location_name,
        "attempted_quantity": quantity,
    }
    ctrl = notifications.notify_role(
        db, Role.STATE_DRUG_CONTROLLER, type_="REENTRY_FRAUD", payload=payload,
        channels=["in_app", "email", "sms"], batch_id=batch.id,
    )
    mfr = notifications.notify(
        db,
        recipient=manufacturer,
        recipient_label=f"MANUFACTURER:{manufacturer.name}" if manufacturer else "MANUFACTURER",
        type_="REENTRY_FRAUD",
        payload=payload,
        channels=["in_app", "email", "sms"],
        batch_id=batch.id,
    )
    alert.notified_controller = bool(ctrl)
    alert.notified_manufacturer = bool(mfr)

    registry.record_event(
        db, event_type="REENTRY_BLOCKED", batch=batch, actor=None,
        payload={**payload, "pos_transaction_id": pos_txn.id},
    )

    db.flush()
    alert.notification_latency_ms = int((time.perf_counter() - t0) * 1000)
    db.add(alert)
    db.flush()

    from app.services import events

    events.enqueue(
        db, "reentry", action="blocked", alert_id=alert.id, batch_id=batch.id,
        batch_number=batch.batch_number, retailer_id=retailer.id,
        manufacturer_id=batch.manufacturer_id, at=str(alert.triggered_at or ""),
    )
    return alert
