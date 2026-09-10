from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbDep
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas import LoginIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DbDep):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalars().first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(user.id, user.role, {"name": user.name})
    return TokenOut(access_token=token, role=user.role, name=user.name, user_id=user.id)


@router.get("/me")
def me(user: CurrentUser, db: DbDep):
    lic = user.license
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "location": user.location_name,
        "mapped_distributor_id": user.mapped_distributor_id,
        "mapped_manufacturer_id": user.mapped_manufacturer_id,
        "license": None
        if not lic
        else {
            "license_number": lic.license_number,
            "entity_type": lic.entity_type,
            "state": lic.state,
            "status": lic.status,
            "valid_until": lic.valid_until,
        },
    }
