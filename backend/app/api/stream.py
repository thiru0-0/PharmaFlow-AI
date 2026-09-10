from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.base import SessionLocal
from app.models import BatchHolding, Batch, ReturnRequest, Role, User
from app.services import events

log = logging.getLogger("pharmaflow.stream")
router = APIRouter(tags=["stream"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
}


def _scope_batch_ids(db: Session, user: User) -> set[str] | None:
    """None = sees everything (regulator / admin)."""
    if user.role in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        return None
    if user.role == Role.MANUFACTURER.value:
        return set(db.execute(select(Batch.id).where(Batch.manufacturer_id == user.id)).scalars().all())
    if user.role == Role.RETAILER.value:
        return set(db.execute(select(BatchHolding.batch_id).where(BatchHolding.retailer_id == user.id)).scalars().all())
    if user.role == Role.DISTRIBUTOR.value:
        return set(db.execute(select(ReturnRequest.batch_id).where(ReturnRequest.distributor_id == user.id)).scalars().all())
    return set()


def _load_context(uid: str) -> tuple[User | None, set[str] | None]:
    db = SessionLocal()
    try:
        user = db.get(User, uid)
        return (user, _scope_batch_ids(db, user)) if user else (None, None)
    finally:
        db.close()


def _visible_to(evt: dict, user: User, scope: set[str] | None) -> bool:
    if scope is None:  # regulator / admin
        return True
    if evt.get("kind") == "notification":
        if evt.get("recipient_id") == user.id:
            return True
        label = evt.get("recipient_label") or ""
        return label.startswith(user.role)
    bid = evt.get("batch_id")
    if bid and bid in scope:
        return True
    for f in ("retailer_id", "distributor_id", "manufacturer_id", "actor_id"):
        if evt.get(f) and evt.get(f) == user.id:
            return True
    return False


@router.get("/stream")
async def stream(request: Request, token: str = Query(...)):
    """Server-Sent Events. EventSource can't set headers, so the JWT rides in ?token=."""
    try:
        payload = decode_token(token)
    except Exception:
        return StreamingResponse(
            iter(["event: error\ndata: unauthorized\n\n"]),
            media_type="text/event-stream", status_code=401, headers=_SSE_HEADERS,
        )

    uid = payload.get("sub")
    user, scope = await asyncio.to_thread(_load_context, uid)
    if user is None:
        return StreamingResponse(
            iter(["event: error\ndata: unknown user\n\n"]),
            media_type="text/event-stream", status_code=401, headers=_SSE_HEADERS,
        )

    q = events.subscribe()

    async def gen():
        nonlocal scope
        yield "retry: 3000\n\n"
        yield f"event: hello\ndata: {json.dumps({'role': user.role})}\n\n"
        last_refresh = asyncio.get_event_loop().time()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                now = asyncio.get_event_loop().time()
                if now - last_refresh > 15:
                    _, fresh = await asyncio.to_thread(_load_context, uid)
                    if fresh is not None or scope is not None:
                        scope = fresh
                    last_refresh = now

                if _visible_to(evt, user, scope):
                    yield f"event: message\ndata: {json.dumps(evt, default=str)}\n\n"
        except asyncio.CancelledError:  # pragma: no cover
            pass
        finally:
            events.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)
