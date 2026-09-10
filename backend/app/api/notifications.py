from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select, update

from app.core.deps import CurrentUser, DbDep
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _mine(user):
    return or_(
        Notification.recipient_id == user.id,
        Notification.recipient_label.like(f"{user.role}%"),
    )


@router.get("")
def list_notifications(user: CurrentUser, db: DbDep, limit: int = 30):
    rows = db.execute(
        select(Notification)
        .where(Notification.channel == "in_app", _mine(user))
        .order_by(Notification.created_at.desc())
        .limit(min(limit, 100))
    ).scalars().all()
    unread = db.execute(
        select(Notification)
        .where(Notification.channel == "in_app", _mine(user), Notification.read.is_(False))
    ).scalars().all()
    return {
        "unread_count": len(unread),
        "items": [
            {
                "id": n.id, "type": n.type, "channel": n.channel,
                "delivery_status": n.delivery_status, "payload": n.payload,
                "read": n.read, "created_at": n.created_at, "batch_id": n.batch_id,
                "recipient": n.recipient_label,
            }
            for n in rows
        ],
    }


@router.post("/{nid}/read")
def mark_read(nid: str, user: CurrentUser, db: DbDep):
    n = db.get(Notification, nid)
    if not n:
        raise HTTPException(404, "Notification not found")
    n.read = True
    db.add(n)
    db.commit()
    return {"status": "read"}


@router.post("/read-all")
def mark_all_read(user: CurrentUser, db: DbDep):
    res = db.execute(
        update(Notification)
        .where(Notification.channel == "in_app", _mine(user), Notification.read.is_(False))
        .values(read=True)
    )
    db.commit()
    return {"status": "ok", "marked": res.rowcount}
