"""In-process real-time event bus.

Sync request handlers (run in Starlette's threadpool) enqueue events onto the SQLAlchemy
session; a single ``after_commit`` listener fans them out to every connected SSE client,
so subscribers never see an event before its transaction is durable.

For a single backend process this is all that's needed. To scale to multiple workers,
bridge :func:`publish` to Postgres ``LISTEN/NOTIFY`` (see ROADMAP).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from app.db.base import SessionLocal

log = logging.getLogger("pharmaflow.events")

_loop: asyncio.AbstractEventLoop | None = None
_subscribers: set[asyncio.Queue] = set()
_MAX_QUEUE = 500


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once from the app lifespan so cross-thread publishing can reach the loop."""
    global _loop
    _loop = loop


def subscriber_count() -> int:
    return len(_subscribers)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def _fanout(evt: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:  # slow client — drop its oldest event
            with contextlib.suppress(Exception):
                q.get_nowait()
                q.put_nowait(evt)


def publish(kind: str, **fields: Any) -> None:
    """Thread-safe immediate publish. Prefer :func:`enqueue` from inside a transaction."""
    if _loop is None or not _subscribers:
        return
    evt = {"kind": kind, **fields}
    with contextlib.suppress(RuntimeError):
        _loop.call_soon_threadsafe(_fanout, evt)


def enqueue(session: Session, kind: str, **fields: Any) -> None:
    """Stage an event to be published when the session's transaction commits."""
    session.info.setdefault("_pf_pending", []).append({"kind": kind, **fields})


@sa_event.listens_for(SessionLocal, "after_commit")
def _emit_pending(session: Session) -> None:  # pragma: no cover - timing
    pending = session.info.pop("_pf_pending", [])
    for evt in pending:
        publish(evt.pop("kind"), **evt)


@sa_event.listens_for(SessionLocal, "after_rollback")
def _drop_pending(session: Session) -> None:  # pragma: no cover - timing
    session.info.pop("_pf_pending", None)
