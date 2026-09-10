"""Notification abstraction. Mock providers by default — no external credentials needed.

Every send is persisted to `notifications` with a delivery_status the UI can render
("sent" for in-app, "simulated" for email/SMS when no provider configured).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Notification, Role, User


def _provider_status(channel: str) -> str:
    if channel == "in_app":
        return "sent"
    if channel == "email":
        return "sent" if settings.SMTP_HOST else "simulated"
    if channel == "sms":
        return "sent" if settings.SMS_PROVIDER_URL else "simulated"
    return "simulated"


def notify(
    db: Session,
    *,
    recipient: User | None,
    recipient_label: str,
    type_: str,
    payload: dict,
    channels: list[str],
    batch_id: str | None = None,
) -> list[Notification]:
    from app.services import events

    out = []
    for ch in channels:
        n = Notification(
            recipient_id=recipient.id if recipient else None,
            recipient_label=recipient_label,
            type=type_,
            channel=ch,
            payload=payload,
            delivery_status=_provider_status(ch),
            batch_id=batch_id,
        )
        db.add(n)
        out.append(n)
    db.flush()

    for n in out:
        if n.channel == "in_app":
            events.enqueue(
                db, "notification",
                id=n.id, recipient_id=n.recipient_id, recipient_label=n.recipient_label,
                type=n.type, payload=n.payload, batch_id=n.batch_id,
                at=str(n.created_at or ""),
            )
    return out


def notify_role(
    db: Session, role: Role, *, type_: str, payload: dict, channels: list[str], batch_id: str | None = None
) -> list[Notification]:
    users = db.execute(select(User).where(User.role == role.value)).scalars().all()
    out = []
    for u in users:
        out += notify(
            db, recipient=u, recipient_label=f"{role.value}:{u.name}", type_=type_,
            payload=payload, channels=channels, batch_id=batch_id,
        )
    if not users:
        out += notify(
            db, recipient=None, recipient_label=role.value, type_=type_,
            payload=payload, channels=channels, batch_id=batch_id,
        )
    return out
