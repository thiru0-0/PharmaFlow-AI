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
    connect_args = {"connect_timeout": 10, "application_name": "pharmaflow"}
    engine_kwargs.update(
        pool_pre_ping=False,
        pool_size=10,
        max_overflow=20,
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
