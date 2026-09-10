from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.base import SessionLocal
from app.services import expiry, registry, sla

log = logging.getLogger("pharmaflow.jobs")
_scheduler: BackgroundScheduler | None = None


def _run(fn_name, fn):
    db = SessionLocal()
    try:
        result = fn(db)
        log.info("job %s: %s", fn_name, result)
    except Exception:  # pragma: no cover
        log.exception("job %s failed", fn_name)
    finally:
        db.close()


def _verify(db):
    return registry.verify_all(db)


def _checkpoint(db):
    cp = registry.build_checkpoint(db)
    db.commit()
    return {"checkpoint": cp.merkle_root if cp else None}


def start() -> None:
    global _scheduler
    if _scheduler:
        return
    demo = settings.APP_ENV == "demo"
    _scheduler = BackgroundScheduler(timezone="UTC")
    # In demo mode the jobs run on a tight loop so a live audience sees the network breathe.
    _scheduler.add_job(lambda: _run("expiry", expiry.run), "interval",
                       seconds=90 if demo else 6 * 3600, id="expiry")
    _scheduler.add_job(lambda: _run("sla", sla.scan), "interval",
                       seconds=150 if demo else 6 * 3600, id="sla")
    _scheduler.add_job(lambda: _run("verify", _verify), "interval",
                       seconds=120 if demo else 1800, id="verify")
    _scheduler.add_job(lambda: _run("checkpoint", _checkpoint), "interval",
                       seconds=300 if demo else 3600, id="checkpoint")
    _scheduler.start()
    log.info("scheduler started (demo=%s)", demo)


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
