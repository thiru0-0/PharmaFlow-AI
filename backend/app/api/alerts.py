from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep
from app.models import Batch, ReentryAlert, Role, User, utcnow
from app.schemas import ResolveAlertIn
from app.services import registry

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/reentry")
def list_reentry(user: CurrentUser, db: DbDep):
    q = select(ReentryAlert).order_by(ReentryAlert.triggered_at.desc())
    alerts = db.execute(q).scalars().all()
    out = []
    for a in alerts:
        batch = db.get(Batch, a.batch_id)
        if user.role == Role.MANUFACTURER.value and batch.manufacturer_id != user.id:
            continue
        if user.role == Role.RETAILER.value and a.attempted_retailer_id != user.id:
            continue
        if user.role == Role.DISTRIBUTOR.value:
            continue
        out.append(_view(a, batch))
    return out


def _view(a: ReentryAlert, batch: Batch) -> dict:
    return {
        "id": a.id,
        "severity": a.severity,
        "status": a.status,
        "batch_number": a.batch_number,
        "manufacturer_license_id": batch.manufacturer_license_id,
        "batch_state_at_attempt": a.batch_state_at_attempt,
        "attempted_retailer": a.attempted_retailer_name,
        "attempted_location": a.attempted_location,
        "origin_location": a.origin_location,
        "attempted_quantity": a.attempted_quantity,
        "notified_controller": a.notified_controller,
        "notified_manufacturer": a.notified_manufacturer,
        "notification_latency_ms": a.notification_latency_ms,
        "triggered_at": a.triggered_at,
        "resolved_at": a.resolved_at,
        "resolution_notes": a.resolution_notes,
    }


@router.get("/reentry/{alert_id}")
def get_reentry(alert_id: str, user: CurrentUser, db: DbDep):
    a = db.get(ReentryAlert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    return _view(a, db.get(Batch, a.batch_id))


@router.post("/reentry/{alert_id}/resolve")
def resolve_reentry(alert_id: str, body: ResolveAlertIn, user: CurrentUser, db: DbDep):
    if user.role not in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        raise HTTPException(403, "Only the state drug controller / admin can close an investigation")
    a = db.get(ReentryAlert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    if a.status == "RESOLVED":
        raise HTTPException(409, "Alert already resolved")
    a.status = "RESOLVED"
    a.resolution_notes = body.resolution_notes
    a.resolved_at = utcnow()
    db.add(a)
    batch = db.get(Batch, a.batch_id)
    # resolution appends an event — never erases the original alert
    registry.record_event(
        db, event_type="REENTRY_ALERT_RESOLVED", batch=batch, actor=user,
        payload={"alert_id": a.id, "resolution_notes": body.resolution_notes},
    )
    db.commit()
    return {"status": "RESOLVED", "alert_id": a.id}
