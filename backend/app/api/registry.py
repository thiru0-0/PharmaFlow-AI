from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep
from app.models import Batch, RegistryCheckpoint, RegistryEvent, Role, User
from app.services import registry as reg

router = APIRouter(prefix="/registry", tags=["registry"])


def _scoped_batches(db, user: User):
    if user.role in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        return None  # all
    q = select(Batch.id)
    if user.role == Role.MANUFACTURER.value:
        return set(db.execute(q.where(Batch.manufacturer_id == user.id)).scalars().all())
    from app.models import BatchHolding, ReturnRequest

    if user.role == Role.RETAILER.value:
        return set(db.execute(
            select(BatchHolding.batch_id).where(BatchHolding.retailer_id == user.id)
        ).scalars().all())
    if user.role == Role.DISTRIBUTOR.value:
        return set(db.execute(
            select(ReturnRequest.batch_id).where(ReturnRequest.distributor_id == user.id)
        ).scalars().all())
    return set()


def _find_batch(db, batch_number: str, manufacturer_license_id: str | None) -> Batch:
    q = select(Batch).where(Batch.batch_number == batch_number)
    if manufacturer_license_id:
        q = q.where(Batch.manufacturer_license_id == manufacturer_license_id)
    batches = db.execute(q).scalars().all()
    if not batches:
        raise HTTPException(404, "No batch with that number in the registry")
    if len(batches) > 1:
        raise HTTPException(
            409,
            "Ambiguous batch number across manufacturers — pass manufacturer_license_id "
            f"(candidates: {[b.manufacturer_license_id for b in batches]})",
        )
    return batches[0]


@router.get("/batches/{batch_number}/history")
def batch_history(
    batch_number: str, user: CurrentUser, db: DbDep,
    manufacturer_license_id: str | None = Query(None),
):
    batch = _find_batch(db, batch_number, manufacturer_license_id)
    scope = _scoped_batches(db, user)
    if scope is not None and batch.id not in scope:
        raise HTTPException(403, "Not permitted to view this batch")
    events = db.execute(
        select(RegistryEvent).where(RegistryEvent.batch_id == batch.id).order_by(RegistryEvent.seq)
    ).scalars().all()
    return {
        "batch_number": batch.batch_number,
        "manufacturer_license_id": batch.manufacturer_license_id,
        "drug_name": batch.drug_name,
        "current_state": batch.state,
        "flagged_at": batch.flagged_at,
        "non_compliant": batch.non_compliant,
        "reentry_flagged": batch.reentry_flagged,
        "events": [
            {
                "seq": e.seq, "event_type": e.event_type, "actor": e.actor_name,
                "payload": e.payload, "prev_hash": e.prev_hash, "hash": e.hash,
                "signature": e.signature[:32] + "...", "created_at": e.created_at,
            }
            for e in events
        ],
    }


@router.get("/verify/{batch_number}")
def verify(batch_number: str, user: CurrentUser, db: DbDep,
           manufacturer_license_id: str | None = Query(None)):
    batch = _find_batch(db, batch_number, manufacturer_license_id)
    return reg.verify_batch_chain(db, batch)


@router.get("/verify-all")
def verify_all(user: CurrentUser, db: DbDep):
    if user.role not in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        raise HTTPException(403, "Regulator/admin only")
    return reg.verify_all(db)


@router.get("/events")
def events(
    user: CurrentUser, db: DbDep,
    batch_number: str | None = None, event_type: str | None = None,
    actor_id: str | None = None, limit: int = 100,
):
    q = select(RegistryEvent).order_by(RegistryEvent.id.desc()).limit(min(limit, 500))
    if batch_number:
        q = q.where(RegistryEvent.batch_number == batch_number)
    if event_type:
        q = q.where(RegistryEvent.event_type == event_type)
    if actor_id:
        q = q.where(RegistryEvent.actor_id == actor_id)
    rows = db.execute(q).scalars().all()
    scope = _scoped_batches(db, user)
    out = []
    for e in rows:
        if scope is not None and e.batch_id not in scope:
            continue
        out.append({
            "id": e.id, "seq": e.seq, "event_type": e.event_type, "actor": e.actor_name,
            "batch_number": e.batch_number, "hash": e.hash, "prev_hash": e.prev_hash,
            "signature": e.signature[:24] + "...", "created_at": e.created_at,
        })
    return out


@router.get("/checkpoints")
def checkpoints(user: CurrentUser, db: DbDep):
    rows = db.execute(
        select(RegistryCheckpoint).order_by(RegistryCheckpoint.id.desc()).limit(50)
    ).scalars().all()
    return [
        {"id": c.id, "merkle_root": c.merkle_root, "event_count": c.event_count,
         "from_event_id": c.from_event_id, "to_event_id": c.to_event_id, "created_at": c.created_at}
        for c in rows
    ]


@router.post("/checkpoints/build")
def build_checkpoint(user: CurrentUser, db: DbDep):
    if user.role not in (Role.ADMIN.value, Role.STATE_DRUG_CONTROLLER.value):
        raise HTTPException(403, "Regulator/admin only")
    cp = reg.build_checkpoint(db)
    db.commit()
    if not cp:
        return {"status": "no new events"}
    return {"status": "checkpoint created", "merkle_root": cp.merkle_root, "event_count": cp.event_count}
