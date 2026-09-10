"""Hash-chained, Ed25519-signed, append-only registry.

Tamper-evident (NOT a blockchain). Each batch has its own chain of events ordered by `seq`.

    hash = SHA256(prev_hash + canonical_json(payload) + created_at_iso)

`created_at_iso` is also embedded in payload["_ts"] so verification is independent of how
the database stores timestamps.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Batch, RegistryCheckpoint, RegistryEvent, User
from app.services import keys

GENESIS = "0" * 64


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev_hash: str, payload: dict, created_at_iso: str) -> str:
    return hashlib.sha256(
        (prev_hash + canonical_json(payload) + created_at_iso).encode()
    ).hexdigest()


def record_event(
    db: Session,
    *,
    event_type: str,
    batch: Batch,
    actor: User | None,
    payload: dict,
) -> RegistryEvent:
    """Append one signed event to a batch's chain. Caller commits."""
    prev = (
        db.execute(
            select(RegistryEvent)
            .where(RegistryEvent.batch_id == batch.id)
            .order_by(RegistryEvent.seq.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    prev_hash = prev.hash if prev else GENESIS
    seq = (prev.seq + 1) if prev else 0

    created_at = datetime.now(timezone.utc)
    created_at_iso = created_at.isoformat()

    full_payload = dict(payload)
    full_payload["_ts"] = created_at_iso
    full_payload["_event_type"] = event_type

    h = _hash(prev_hash, full_payload, created_at_iso)

    # Sign with the actor's license key; system events use the platform admin key.
    if actor and actor.license_id:
        signer_license = actor.license_id
        signer_name = actor.name
    else:
        signer_license = _system_license_id(db)
        signer_name = "system"
    signer_pub = keys.ensure_keypair(signer_license)
    signature = keys.sign(signer_license, h)

    evt = RegistryEvent(
        event_type=event_type,
        actor_id=actor.id if actor else None,
        actor_name=signer_name,
        batch_id=batch.id,
        batch_number=batch.batch_number,
        manufacturer_license_id=batch.manufacturer_license_id,
        payload=full_payload,
        prev_hash=prev_hash,
        hash=h,
        signature=signature,
        signer_public_key=signer_pub,
        created_at=created_at,
        seq=seq,
    )
    db.add(evt)
    db.flush()
    return evt


def _system_license_id(db: Session) -> str:
    admin = db.execute(
        select(User).where(User.role == "ADMIN").limit(1)
    ).scalars().first()
    if admin and admin.license_id:
        return admin.license_id
    return "system-registry"


def verify_batch_chain(db: Session, batch: Batch) -> dict:
    events = (
        db.execute(
            select(RegistryEvent)
            .where(RegistryEvent.batch_id == batch.id)
            .order_by(RegistryEvent.seq.asc())
        )
        .scalars()
        .all()
    )
    problems: list[dict] = []
    prev_hash = GENESIS
    prev_ts: datetime | None = None

    for i, e in enumerate(events):
        if e.seq != i:
            problems.append({"seq": e.seq, "issue": f"out-of-order seq (expected {i})"})
        if e.prev_hash != prev_hash:
            problems.append(
                {"seq": e.seq, "issue": "prev_hash mismatch (chain broken / event inserted or removed)"}
            )
        ts_iso = e.payload.get("_ts")
        recomputed = _hash(e.prev_hash, e.payload, ts_iso)
        if recomputed != e.hash:
            problems.append({"seq": e.seq, "issue": "hash mismatch (payload tampered)"})
        if not keys.verify(e.signer_public_key, e.hash, e.signature):
            problems.append({"seq": e.seq, "issue": "signature invalid (signature or hash tampered)"})
        # chronological ordering
        try:
            cur_ts = datetime.fromisoformat(ts_iso)
            if prev_ts and cur_ts < prev_ts:
                problems.append({"seq": e.seq, "issue": "timestamp earlier than previous event"})
            prev_ts = cur_ts
        except Exception:
            problems.append({"seq": e.seq, "issue": "unparseable timestamp"})
        prev_hash = e.hash

    return {
        "batch_number": batch.batch_number,
        "manufacturer_license_id": batch.manufacturer_license_id,
        "event_count": len(events),
        "hash_chain_valid": not any("hash" in p["issue"] or "prev_hash" in p["issue"] for p in problems),
        "signatures_valid": not any("signature" in p["issue"] for p in problems),
        "ordering_valid": not any("order" in p["issue"] or "timestamp" in p["issue"] for p in problems),
        "valid": len(problems) == 0,
        "problems": problems,
    }


def _merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return GENESIS
    layer = list(hashes)
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [
            hashlib.sha256((layer[i] + layer[i + 1]).encode()).hexdigest()
            for i in range(0, len(layer), 2)
        ]
    return layer[0]


def build_checkpoint(db: Session) -> RegistryCheckpoint | None:
    last = (
        db.execute(select(RegistryCheckpoint).order_by(RegistryCheckpoint.to_event_id.desc()).limit(1))
        .scalars()
        .first()
    )
    from_id = (last.to_event_id + 1) if last else 1
    new_events = (
        db.execute(
            select(RegistryEvent).where(RegistryEvent.id >= from_id).order_by(RegistryEvent.id.asc())
        )
        .scalars()
        .all()
    )
    if not new_events:
        return None
    cp = RegistryCheckpoint(
        merkle_root=_merkle_root([e.hash for e in new_events]),
        event_count=len(new_events),
        from_event_id=new_events[0].id,
        to_event_id=new_events[-1].id,
    )
    db.add(cp)
    db.flush()
    return cp


def verify_all(db: Session) -> dict:
    batches = db.execute(select(Batch)).scalars().all()
    results = [verify_batch_chain(db, b) for b in batches]
    total_events = db.execute(select(func.count(RegistryEvent.id))).scalar_one()
    breaches = [r for r in results if not r["valid"]]
    return {
        "batches_checked": len(results),
        "total_events": total_events,
        "breaches": breaches,
        "healthy": len(breaches) == 0,
    }
