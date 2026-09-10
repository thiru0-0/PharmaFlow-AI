from __future__ import annotations

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Batch,
    BatchHolding,
    BatchState,
    ReturnRequest,
    ReturnStatus,
    Role,
    User,
    utcnow,
)
from app.services import batch_state, notifications


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def run(db: Session) -> dict:
    """Idempotent daily job: 60-day alerts + auto return-request on expiry crossing.

    Running twice must never duplicate an alert or a return request.
    """
    now = utcnow()
    today = now.date()
    alerts_sent = 0
    returns_created = 0

    holdings = db.execute(
        select(BatchHolding).where(BatchHolding.quantity_on_hand > 0)
    ).scalars().all()

    for h in holdings:
        batch = db.get(Batch, h.batch_id)
        if batch is None or BatchState(batch.state) != BatchState.ACTIVE:
            continue
        days_to_expiry = (_aware(batch.expiry_date).date() - today).days

        # 60-day pre-expiry alert — fire once
        if days_to_expiry <= settings.EXPIRY_ALERT_DAYS and days_to_expiry >= 0 and not h.expiry_alert_sent:
            retailer = db.get(User, h.retailer_id)
            notifications.notify(
                db, recipient=retailer, recipient_label=f"RETAILER:{retailer.name}",
                type_="EXPIRY_60_DAY", channels=["in_app", "sms"],
                payload={
                    "batch_number": batch.batch_number, "drug_name": batch.drug_name,
                    "days_to_expiry": days_to_expiry, "quantity_on_hand": h.quantity_on_hand,
                },
                batch_id=batch.id,
            )
            h.expiry_alert_sent = True
            db.add(h)
            alerts_sent += 1

        # Expiry crossed -> auto return request (idempotent: skip if an open one exists)
        if days_to_expiry <= 0:
            existing = db.execute(
                select(ReturnRequest).where(
                    ReturnRequest.batch_id == batch.id,
                    ReturnRequest.retailer_id == h.retailer_id,
                    ReturnRequest.status != ReturnStatus.CLOSED.value,
                )
            ).scalars().first()
            if existing:
                continue
            retailer = db.get(User, h.retailer_id)
            distributor_id = retailer.mapped_distributor_id
            if not distributor_id:
                continue
            rr = ReturnRequest(
                batch_id=batch.id,
                retailer_id=h.retailer_id,
                distributor_id=distributor_id,
                quantity_reported=None,
                status=ReturnStatus.AUTO_CREATED.value,
                expiry_date=batch.expiry_date,
            )
            db.add(rr)
            db.flush()
            batch_state.transition(
                db, batch, BatchState.RETURN_INITIATED, actor=None,
                event_type="RETURN_AUTO_CREATED",
                payload={"return_request_id": rr.id, "retailer_id": h.retailer_id,
                         "distributor_id": distributor_id, "trigger": "expiry_crossed"},
            )
            notifications.notify(
                db, recipient=retailer, recipient_label=f"RETAILER:{retailer.name}",
                type_="RETURN_AUTO_CREATED", channels=["in_app"],
                payload={"batch_number": batch.batch_number, "return_request_id": rr.id,
                         "action_required": "Attach condition photo + confirm counted quantity"},
                batch_id=batch.id,
            )
            dist = db.get(User, distributor_id)
            notifications.notify(
                db, recipient=dist, recipient_label=f"DISTRIBUTOR:{dist.name}",
                type_="RETURN_AUTO_CREATED", channels=["in_app"],
                payload={"batch_number": batch.batch_number, "return_request_id": rr.id,
                         "retailer": retailer.name},
                batch_id=batch.id,
            )
            returns_created += 1

    db.commit()
    return {"alerts_sent": alerts_sent, "returns_created": returns_created}
