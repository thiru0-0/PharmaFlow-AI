from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbDep, require_roles
from app.models import (
    Batch,
    BatchState,
    Dispute,
    DisputeStatus,
    Pickup,
    PickupRoute,
    PickupStatus,
    ReturnRequest,
    ReturnStatus,
    Role,
    User,
    utcnow,
)
from app.schemas import PickupConfirmIn, RouteOptimizeIn
from app.services import batch_state, registry
from app.services.route_optimizer import Stop, optimize

router = APIRouter(prefix="/distributor", tags=["distributor"])
dist_only = Depends(require_roles(Role.DISTRIBUTOR))


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _tolerance_units(reported: int) -> float:
    return max(settings.QTY_TOLERANCE_MIN_UNITS, reported * settings.QTY_TOLERANCE_PCT / 100.0)


@router.get("/returns/pending")
def pending_returns(user: CurrentUser, db: DbDep, _=dist_only):
    rows = db.execute(
        select(ReturnRequest, Batch, User)
        .join(Batch, Batch.id == ReturnRequest.batch_id)
        .join(User, User.id == ReturnRequest.retailer_id)
        .where(
            ReturnRequest.distributor_id == user.id,
            ReturnRequest.status.in_(
                [ReturnStatus.AUTO_CREATED.value, ReturnStatus.RETURN_INITIATED.value,
                 ReturnStatus.PICKUP_SCHEDULED.value]
            ),
        )
    ).all()
    now = utcnow()
    out = []
    for rr, b, r in rows:
        days_since_expiry = (now - _aware(rr.expiry_date)).days
        sla_days_left = settings.RETAILER_RETURN_WINDOW_DAYS - days_since_expiry
        out.append(
            {
                "return_id": rr.id,
                "batch_id": b.id,
                "batch_number": b.batch_number,
                "drug_name": b.drug_name,
                "batch_state": b.state,
                "retailer_id": r.id,
                "retailer_name": r.name,
                "retailer_location": r.location_name,
                "lat": r.lat,
                "lng": r.lng,
                "quantity_reported": rr.quantity_reported,
                "status": rr.status,
                "sla_days_left": sla_days_left,
                "urgency": round(max(0.0, min(1.0, 1 - sla_days_left / max(1, settings.RETAILER_RETURN_WINDOW_DAYS))), 3),
            }
        )
    return out


@router.post("/routes/optimize")
def optimize_route(body: RouteOptimizeIn, user: CurrentUser, db: DbDep, _=dist_only):
    pend = pending_returns(user, db, _=None)  # type: ignore
    schedulable = [p for p in pend if p["quantity_reported"] and p["lat"] is not None]
    if not schedulable:
        raise HTTPException(400, "No confirmed pending returns with location + quantity to route")

    depot = (user.lat or 19.076, user.lng or 72.877)
    stops = [
        Stop(p["retailer_id"], p["retailer_name"], p["lat"], p["lng"],
             int(p["quantity_reported"]), float(p["urgency"]))
        for p in schedulable
    ]
    result = optimize(depot, stops, body.vehicle_capacity)

    route = PickupRoute(
        distributor_id=user.id,
        algorithm=result["algorithm"],
        stops=result["stops"],
        total_distance_km=result["total_distance_km"],
        total_duration_min=result["total_duration_min"],
        total_cost=result["total_cost"],
        capacity_used=result["capacity_used"],
        vehicle_capacity=result["vehicle_capacity"],
        urgency_score=result["urgency_score"],
    )
    db.add(route)
    db.flush()

    # schedule each stop: create pickup + transition batch RETURN_INITIATED -> PICKUP_SCHEDULED
    for p in schedulable:
        rr = db.get(ReturnRequest, p["return_id"])
        batch = db.execute(select(Batch).where(Batch.id == rr.batch_id).with_for_update()).scalars().one()
        existing = db.execute(select(Pickup).where(Pickup.return_request_id == rr.id)).scalars().first()
        if existing is None:
            db.add(Pickup(return_request_id=rr.id, distributor_id=user.id, route_id=route.id,
                          status=PickupStatus.SCHEDULED.value))
        rr.status = ReturnStatus.PICKUP_SCHEDULED.value
        db.add(rr)
        if BatchState(batch.state) == BatchState.RETURN_INITIATED:
            batch_state.transition(
                db, batch, BatchState.PICKUP_SCHEDULED, actor=user, event_type="PICKUP_SCHEDULED",
                payload={"route_id": route.id, "return_request_id": rr.id},
            )
    db.commit()
    return {"route_id": route.id, **result}


@router.get("/routes")
def list_routes(user: CurrentUser, db: DbDep, _=dist_only):
    rs = db.execute(
        select(PickupRoute).where(PickupRoute.distributor_id == user.id).order_by(PickupRoute.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": r.id, "algorithm": r.algorithm, "ortools_used": r.algorithm == "ortools_cvrp",
            "stops": r.stops, "total_distance_km": r.total_distance_km,
            "total_duration_min": r.total_duration_min, "total_cost": r.total_cost,
            "capacity_used": r.capacity_used, "vehicle_capacity": r.vehicle_capacity,
            "urgency_score": r.urgency_score, "created_at": r.created_at,
        }
        for r in rs
    ]


@router.get("/pickups")
def list_pickups(user: CurrentUser, db: DbDep, _=dist_only):
    rows = db.execute(
        select(Pickup, ReturnRequest, Batch)
        .join(ReturnRequest, ReturnRequest.id == Pickup.return_request_id)
        .join(Batch, Batch.id == ReturnRequest.batch_id)
        .where(Pickup.distributor_id == user.id)
        .order_by(Pickup.scheduled_at.desc())
    ).all()
    return [
        {
            "pickup_id": p.id, "return_id": rr.id, "batch_id": b.id, "batch_number": b.batch_number,
            "drug_name": b.drug_name, "status": p.status, "batch_state": b.state,
            "quantity_reported": rr.quantity_reported, "quantity_confirmed": p.quantity_confirmed,
        }
        for p, rr, b in rows
    ]


@router.post("/pickups/{pickup_id}/confirm")
def confirm_pickup(pickup_id: str, body: PickupConfirmIn, user: CurrentUser, db: DbDep, _=dist_only):
    pickup = db.execute(select(Pickup).where(Pickup.id == pickup_id).with_for_update()).scalars().first()
    if not pickup or pickup.distributor_id != user.id:
        raise HTTPException(404, "Pickup not found")
    if pickup.status in (PickupStatus.CONFIRMED.value, PickupStatus.RESOLVED.value):
        raise HTTPException(409, f"Pickup already {pickup.status}")
    if body.idempotency_key:
        dup = db.execute(
            select(Pickup).where(Pickup.idempotency_key == body.idempotency_key, Pickup.id != pickup.id)
        ).scalars().first()
        if dup:
            raise HTTPException(409, "Duplicate confirmation (idempotency key already used)")
        pickup.idempotency_key = body.idempotency_key

    rr = db.get(ReturnRequest, pickup.return_request_id)
    if rr.quantity_reported is None:
        raise HTTPException(409, "Retailer has not confirmed the returned quantity yet")
    batch = db.execute(select(Batch).where(Batch.id == rr.batch_id).with_for_update()).scalars().one()

    # auto-schedule if still RETURN_INITIATED (happy path without explicit optimize call)
    if BatchState(batch.state) == BatchState.RETURN_INITIATED:
        batch_state.transition(
            db, batch, BatchState.PICKUP_SCHEDULED, actor=user, event_type="PICKUP_SCHEDULED",
            payload={"return_request_id": rr.id, "note": "auto-scheduled at confirm"},
        )

    pickup.quantity_confirmed = body.quantity_confirmed
    pickup.photo_url = body.photo_url or "mock://uploads/pickup-weight.jpg"
    pickup.confirmed_at = utcnow()

    reported = rr.quantity_reported
    tol = _tolerance_units(reported)
    diff = abs(body.quantity_confirmed - reported)

    if diff > tol:
        pickup.status = PickupStatus.DISPUTED.value
        dispute = Dispute(
            pickup_id=pickup.id, batch_id=batch.id, reported_qty=reported,
            confirmed_qty=body.quantity_confirmed, tolerance_units=tol,
            status=DisputeStatus.OPEN.value,
        )
        db.add(dispute)
        db.flush()
        batch_state.transition(
            db, batch, BatchState.DISPUTED, actor=user, event_type="DISPUTE_RAISED",
            payload={"pickup_id": pickup.id, "dispute_id": dispute.id, "reported_qty": reported,
                     "confirmed_qty": body.quantity_confirmed, "tolerance_units": round(tol, 2)},
        )
        from app.services import notifications

        p = {"batch_number": batch.batch_number, "reported_qty": reported,
             "confirmed_qty": body.quantity_confirmed, "dispute_id": dispute.id}
        notifications.notify(db, recipient=db.get(User, rr.retailer_id),
                             recipient_label="RETAILER", type_="DISPUTE_RAISED", payload=p,
                             channels=["in_app", "sms"], batch_id=batch.id)
        notifications.notify(db, recipient=user, recipient_label="DISTRIBUTOR",
                             type_="DISPUTE_RAISED", payload=p, channels=["in_app", "sms"], batch_id=batch.id)
        db.commit()
        return {"status": "DISPUTED", "dispute_id": dispute.id, "batch_state": batch.state,
                "reported_qty": reported, "confirmed_qty": body.quantity_confirmed,
                "tolerance_units": round(tol, 2), "difference": diff,
                "message": "Quantity mismatch beyond tolerance — batch blocked pending resolution"}

    pickup.status = PickupStatus.CONFIRMED.value
    rr.status = ReturnStatus.PICKED_UP.value
    db.add_all([pickup, rr])
    batch_state.transition(
        db, batch, BatchState.PICKUP_CONFIRMED, actor=user, event_type="PICKUP_CONFIRMED",
        payload={"pickup_id": pickup.id, "quantity_confirmed": body.quantity_confirmed,
                 "reported_qty": reported, "within_tolerance": True},
    )
    db.commit()
    return {"status": "PICKUP_CONFIRMED", "batch_state": batch.state,
            "quantity_confirmed": body.quantity_confirmed}
