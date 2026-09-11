from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {}
engine_kwargs: dict = {"future": True}

if settings.is_sqlite:
    connect_args = {"check_same_thread": False}
    engine_kwargs["pool_pre_ping"] = True
else:
    # Remote Postgres (Supabase pooler): a pre-ping SELECT 1 on every checkout is a full
    # network round-trip and dominates latency. Keep a warm pool and recycle before the
    # pooler's idle timeout instead.
    #
    # Small on purpose: Supabase's free-tier session-mode pooler caps the WHOLE project
    # at 15 concurrent clients, and this app is architecturally locked to a single
    # instance/worker anyway (see events.py — the SSE bus + APScheduler jobs only work
    # as one process). A generous pool here doesn't buy throughput, it just means one
    # process can alone exhaust the pooler's cap under a burst of requests and take down
    # every OTHER connection to the database (including a fresh deploy trying to start
    # up) with "max clients reached in session mode". Keep real headroom instead.
    connect_args = {"connect_timeout": 10, "application_name": "pharmaflow"}
    engine_kwargs.update(
        pool_pre_ping=False,
        pool_size=3,
        max_overflow=2,
        pool_recycle=240,
        pool_timeout=15,
    )

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, **engine_kwargs)


if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover - infra
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=8000")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
