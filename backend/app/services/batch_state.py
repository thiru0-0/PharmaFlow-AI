from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import ALLOWED_TRANSITIONS, Batch, BatchState, User
from app.services import registry


class StateError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_409_CONFLICT, detail)


def transition(
    db: Session,
    batch: Batch,
    to_state: BatchState,
    *,
    actor: User | None,
    event_type: str,
    payload: dict,
) -> None:
    """Service-layer guard for the batch lifecycle. No state may be skipped.

    Records a signed registry event for every accepted transition. Caller commits.
    """
    current = BatchState(batch.state)
    if to_state == current:
        return
    if to_state not in ALLOWED_TRANSITIONS.get(current, set()):
        raise StateError(
            f"Illegal transition {current.value} -> {to_state.value}. "
            f"Allowed: {sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))}"
        )
    batch.state = to_state.value

    # The instant a batch enters RETURN_INITIATED, fraud prevention is live.
    if to_state == BatchState.RETURN_INITIATED and batch.flagged_at is None:
        from app.models import utcnow

        batch.flagged_at = utcnow()

    db.add(batch)
    registry.record_event(
        db, event_type=event_type, batch=batch, actor=actor, payload={**payload, "to_state": to_state.value}
    )


def is_flagged(batch: Batch) -> bool:
    """A batch is 'in the return pipeline' from RETURN_INITIATED onward."""
    return batch.flagged_at is not None and BatchState(batch.state) != BatchState.ACTIVE
