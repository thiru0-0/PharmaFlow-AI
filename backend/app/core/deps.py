from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_token
from app.db.base import get_db
from app.models import LicenseStatus, Role, User

DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.execute(
        select(User).options(joinedload(User.license)).where(User.id == payload.get("sub"))
    ).scalars().first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _check_license_active(user: User) -> None:
    """Regulator/admin roles are not license-gated for read access; entity roles are."""
    if user.role in (Role.STATE_DRUG_CONTROLLER.value, Role.ADMIN.value):
        return
    lic = user.license
    if lic is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No license attached to account")
    if lic.status != LicenseStatus.ACTIVE.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"License {lic.license_number} is {lic.status} — action not permitted",
        )


def require_roles(*roles: Role):
    allowed = {r.value for r in roles}

    def _dep(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role {user.role} not permitted for this action",
            )
        _check_license_active(user)
        return user

    return _dep


def require_active_entity(user: CurrentUser) -> User:
    _check_license_active(user)
    return user
