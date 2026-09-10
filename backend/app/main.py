from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api import (
    alerts,
    auth,
    dashboard,
    demo,
    disputes,
    distributor,
    manufacturer,
    notifications,
    registry,
    retailer,
    stream,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pharmaflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.db.base import Base, engine
    import app.models  # noqa: F401  (register mappers)
    from app.services import events  # noqa: F401  (registers after_commit listener)

    events.bind_loop(asyncio.get_running_loop())
    Base.metadata.create_all(bind=engine)
    # warm one pooled connection so the first real request doesn't pay the TLS handshake
    try:
        from sqlalchemy import text

        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:
        log.exception("db warmup failed")
    if settings.APP_ENV != "test":
        try:
            from app.jobs.scheduler import start

            start()
        except Exception:
            log.exception("scheduler failed to start")
    yield
    try:
        from app.jobs.scheduler import stop

        stop()
    except Exception:
        pass


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error. Check server logs."})


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV,
            "db": "sqlite" if settings.is_sqlite else "postgres"}


for r in (auth, retailer, distributor, manufacturer, disputes, registry, alerts,
          dashboard, notifications, demo, stream):
    app.include_router(r.router)
