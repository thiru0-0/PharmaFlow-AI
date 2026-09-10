from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    user_id: str


class SaleIn(BaseModel):
    qr_payload: str | None = None
    batch_number: str | None = None
    manufacturer_license_id: str | None = None
    quantity: int = Field(gt=0)


class ReturnConfirmIn(BaseModel):
    quantity_reported: int = Field(gt=0)
    condition: str = "sealed"
    photo_url: str | None = None


class RouteOptimizeIn(BaseModel):
    vehicle_capacity: int = Field(gt=0, default=500)


class PickupConfirmIn(BaseModel):
    quantity_confirmed: int = Field(gt=0)
    photo_url: str | None = None
    idempotency_key: str | None = None


class EvidenceIn(BaseModel):
    note: str
    file_url: str | None = None


class ResolveDisputeIn(BaseModel):
    reconciled_qty: int = Field(gt=0)
    resolution_notes: str


class ReceiptIn(BaseModel):
    batch_id: str
    quantity: int = Field(gt=0)


class CertificateIn(BaseModel):
    batch_id: str
    facility_name: str
    cert_url: str
    reason: str = "expired"


class ResolveAlertIn(BaseModel):
    resolution_notes: str
