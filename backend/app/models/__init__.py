from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    RETAILER = "RETAILER"
    DISTRIBUTOR = "DISTRIBUTOR"
    MANUFACTURER = "MANUFACTURER"
    STATE_DRUG_CONTROLLER = "STATE_DRUG_CONTROLLER"
    ADMIN = "ADMIN"


class LicenseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"


class BatchState(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RETURN_INITIATED = "RETURN_INITIATED"
    PICKUP_SCHEDULED = "PICKUP_SCHEDULED"
    DISPUTED = "DISPUTED"
    PICKUP_CONFIRMED = "PICKUP_CONFIRMED"
    RECEIVED_BY_MANUFACTURER = "RECEIVED_BY_MANUFACTURER"
    DESTROYED_CERTIFIED = "DESTROYED_CERTIFIED"


# Ordered lifecycle for "flagged from RETURN_INITIATED onward" checks
STATE_ORDER = {
    BatchState.ACTIVE: 0,
    BatchState.RETURN_INITIATED: 1,
    BatchState.PICKUP_SCHEDULED: 2,
    BatchState.DISPUTED: 2,  # side branch of PICKUP_SCHEDULED
    BatchState.PICKUP_CONFIRMED: 3,
    BatchState.RECEIVED_BY_MANUFACTURER: 4,
    BatchState.DESTROYED_CERTIFIED: 5,
}

ALLOWED_TRANSITIONS: dict[BatchState, set[BatchState]] = {
    BatchState.ACTIVE: {BatchState.RETURN_INITIATED},
    BatchState.RETURN_INITIATED: {BatchState.PICKUP_SCHEDULED},
    BatchState.PICKUP_SCHEDULED: {BatchState.DISPUTED, BatchState.PICKUP_CONFIRMED},
    BatchState.DISPUTED: {BatchState.PICKUP_CONFIRMED},
    BatchState.PICKUP_CONFIRMED: {BatchState.RECEIVED_BY_MANUFACTURER},
    BatchState.RECEIVED_BY_MANUFACTURER: {BatchState.DESTROYED_CERTIFIED},
    BatchState.DESTROYED_CERTIFIED: set(),
}


class ReturnStatus(str, enum.Enum):
    AUTO_CREATED = "AUTO_CREATED"
    RETURN_INITIATED = "RETURN_INITIATED"
    PICKUP_SCHEDULED = "PICKUP_SCHEDULED"
    PICKED_UP = "PICKED_UP"
    CLOSED = "CLOSED"


class PickupStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"


class DisputeStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    license_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(32))  # matches Role for entity roles
    state: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=LicenseStatus.ACTIVE.value)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="license")

    __table_args__ = (
        CheckConstraint(
            "status in ('ACTIVE','SUSPENDED','EXPIRED')", name="ck_license_status"
        ),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), index=True)
    license_id: Mapped[str | None] = mapped_column(ForeignKey("licenses.id"))
    public_key: Mapped[str | None] = mapped_column(Text)  # Ed25519 public key (hex)

    mapped_distributor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    mapped_manufacturer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    location_name: Mapped[str | None] = mapped_column(String(128))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    license: Mapped[License | None] = relationship(back_populates="users")

    __table_args__ = (
        CheckConstraint(
            "role in ('RETAILER','DISTRIBUTOR','MANUFACTURER','STATE_DRUG_CONTROLLER','ADMIN')",
            name="ck_user_role",
        ),
    )


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    drug_name: Mapped[str] = mapped_column(String(128))
    batch_number: Mapped[str] = mapped_column(String(64), index=True)
    manufacturer_license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id"), index=True)
    manufacturer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    mfg_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    category: Mapped[str] = mapped_column(String(64), default="antimicrobial")
    qr_payload: Mapped[str] = mapped_column(String(256), unique=True, index=True)

    state: Mapped[str] = mapped_column(String(32), default=BatchState.ACTIVE.value, index=True)
    non_compliant: Mapped[bool] = mapped_column(Boolean, default=False)
    reentry_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("manufacturer_license_id", "batch_number", name="uq_batch_identity"),
        CheckConstraint(
            "state in ('ACTIVE','RETURN_INITIATED','PICKUP_SCHEDULED','DISPUTED',"
            "'PICKUP_CONFIRMED','RECEIVED_BY_MANUFACTURER','DESTROYED_CERTIFIED')",
            name="ck_batch_state",
        ),
        Index("ix_batch_flagged_state", "state", "flagged_at"),
    )


class BatchHolding(Base):
    __tablename__ = "batch_holdings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    retailer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    expiry_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("batch_id", "retailer_id", name="uq_holding"),
        CheckConstraint("quantity_on_hand >= 0", name="ck_holding_nonneg"),
    )


class PosTransaction(Base):
    __tablename__ = "pos_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    retailer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_pos_qty_pos"),)


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    retailer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    distributor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    quantity_reported: Mapped[int | None] = mapped_column(Integer)
    condition: Mapped[str | None] = mapped_column(String(64))
    photo_url: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default=ReturnStatus.AUTO_CREATED.value)
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Only one OPEN return per batch+retailer (partial unique via app + this guard for non-closed)
        Index("ix_return_open", "batch_id", "retailer_id", "status"),
    )


class Pickup(Base):
    __tablename__ = "pickups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    return_request_id: Mapped[str] = mapped_column(ForeignKey("return_requests.id"), index=True)
    distributor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("pickup_routes.id"))
    quantity_confirmed: Mapped[int | None] = mapped_column(Integer)
    photo_url: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default=PickupStatus.SCHEDULED.value)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pickup_id: Mapped[str] = mapped_column(ForeignKey("pickups.id"), unique=True, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    reported_qty: Mapped[int] = mapped_column(Integer)
    confirmed_qty: Mapped[int] = mapped_column(Integer)
    tolerance_units: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default=DisputeStatus.OPEN.value)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    reconciled_qty: Mapped[int | None] = mapped_column(Integer)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dispute_id: Mapped[str] = mapped_column(ForeignKey("disputes.id"), index=True)
    submitted_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManufacturerReceipt(Base):
    __tablename__ = "manufacturer_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), unique=True, index=True)
    distributor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    manufacturer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DestructionCertificate(Base):
    __tablename__ = "destruction_certificates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), unique=True, index=True)
    # Hard DB gate: certificate cannot exist without a receipt row for the same batch.
    receipt_id: Mapped[str] = mapped_column(
        ForeignKey("manufacturer_receipts.id"), nullable=False
    )
    manufacturer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    facility_name: Mapped[str] = mapped_column(String(128))
    cert_url: Mapped[str] = mapped_column(String(256))
    reason: Mapped[str] = mapped_column(String(128), default="expired")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegistryEvent(Base):
    __tablename__ = "registry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(128), default="system")
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    batch_number: Mapped[str] = mapped_column(String(64), index=True)
    manufacturer_license_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), index=True)
    signature: Mapped[str] = mapped_column(Text)
    signer_public_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # position within batch chain


class RegistryCheckpoint(Base):
    __tablename__ = "registry_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merkle_root: Mapped[str] = mapped_column(String(64))
    event_count: Mapped[int] = mapped_column(Integer)
    from_event_id: Mapped[int] = mapped_column(Integer)
    to_event_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReentryAlert(Base):
    __tablename__ = "reentry_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    batch_number: Mapped[str] = mapped_column(String(64), index=True)
    pos_transaction_id: Mapped[str] = mapped_column(ForeignKey("pos_transactions.id"))
    attempted_retailer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    attempted_retailer_name: Mapped[str] = mapped_column(String(128))
    attempted_location: Mapped[str | None] = mapped_column(String(128))
    origin_location: Mapped[str | None] = mapped_column(String(128))
    attempted_quantity: Mapped[int] = mapped_column(Integer)
    batch_state_at_attempt: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="CRITICAL")
    notified_controller: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_manufacturer: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.OPEN.value)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PickupRoute(Base):
    __tablename__ = "pickup_routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    distributor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    route_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    algorithm: Mapped[str] = mapped_column(String(48), default="ortools_cvrp")
    stops: Mapped[list] = mapped_column(JSON)  # ordered [{retailer_id,name,lat,lng,qty,urgency,seq}]
    total_distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    total_duration_min: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    capacity_used: Mapped[int] = mapped_column(Integer, default=0)
    vehicle_capacity: Mapped[int] = mapped_column(Integer, default=0)
    urgency_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_label: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(48), index=True)
    channel: Mapped[str] = mapped_column(String(16))  # in_app | email | sms
    payload: Mapped[dict] = mapped_column(JSON)
    delivery_status: Mapped[str] = mapped_column(String(16), default="sent")  # sent | simulated | failed
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


__all__ = [
    "Base", "Role", "LicenseStatus", "BatchState", "ReturnStatus", "PickupStatus",
    "DisputeStatus", "AlertStatus", "STATE_ORDER", "ALLOWED_TRANSITIONS", "utcnow",
    "License", "User", "Batch", "BatchHolding", "PosTransaction", "ReturnRequest",
    "Pickup", "Dispute", "DisputeEvidence", "ManufacturerReceipt", "DestructionCertificate",
    "RegistryEvent", "RegistryCheckpoint", "ReentryAlert", "PickupRoute", "Notification",
]
