from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

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
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(lambda: _run("expiry", expiry.run), "interval", hours=6, id="expiry")
    _scheduler.add_job(lambda: _run("sla", sla.scan), "interval", hours=6, id="sla")
    _scheduler.add_job(lambda: _run("verify", _verify), "interval", minutes=30, id="verify")
    _scheduler.add_job(lambda: _run("checkpoint", _checkpoint), "interval", hours=1, id="checkpoint")
    _scheduler.start()
    log.info("scheduler started")


def stop() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
