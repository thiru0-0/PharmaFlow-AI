from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbDep, require_roles
from app.models import Role
from app.services import demo as demo_svc
from app.services import scenarios
from app.services.demo import ACCOUNTS, DEMO_PASSWORD

router = APIRouter(prefix="/demo", tags=["demo"])
admin_only = Depends(require_roles(Role.ADMIN))


@router.get("/accounts")
def accounts():
    return [
        {"name": n, "email": e, "password": DEMO_PASSWORD, "role": r.value, "location": loc}
        for (n, e, r, loc, *_rest) in ACCOUNTS
    ]


@router.post("/reset")
def reset(user: CurrentUser, db: DbDep, _=admin_only):
    return demo_svc.seed(db)


@router.post("/scripts/fraud")
def run_fraud(user: CurrentUser, db: DbDep, _=admin_only):
    return scenarios.run_fraud(db)


@router.post("/scripts/happy")
def run_happy(user: CurrentUser, db: DbDep, _=admin_only):
    return scenarios.run_happy(db)


@router.post("/scripts/dispute")
def run_dispute(user: CurrentUser, db: DbDep, _=admin_only):
    return scenarios.run_dispute(db)


@router.post("/scripts/pulse")
def run_pulse(user: CurrentUser, db: DbDep, _=admin_only):
    return scenarios.run_pulse(db)


@router.post("/jobs/expiry")
def run_expiry(user: CurrentUser, db: DbDep, _=admin_only):
    from app.services import expiry

    return expiry.run(db)


@router.post("/jobs/sla")
def run_sla(user: CurrentUser, db: DbDep, _=admin_only):
    from app.services import sla

    return sla.scan(db)


@router.post("/jobs/verify")
def run_verify(user: CurrentUser, db: DbDep, _=admin_only):
    from app.services import registry

    return registry.verify_all(db)
