"""Synthetic JWT authentication and server-enforced RBAC.

Tokens are issued for SYNTHETIC users only. Authorization is enforced here on
the server — the Angular UI hiding a button is never the only guard.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.domain import User
from app.models.enums import Role

_settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def hash_password(raw: str) -> str:
    # bcrypt hard-caps the input at 72 bytes; truncate defensively.
    return bcrypt.hashpw(raw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8")[:72], hashed.encode("utf-8"))


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_settings.jwt_expire_minutes)
    payload = {"sub": user.id, "role": user.role.value, "email": user.email, "exp": expire}
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_token", "message": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
    except JWTError as exc:
        raise credentials_error from exc
    if not user_id:
        raise credentials_error
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise credentials_error
    return user


def require_roles(*roles: Role):
    """Dependency factory: 403 unless the caller holds one of the given roles."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": f"Requires role in {[r.value for r in roles]}",
                    "your_role": user.role.value,
                },
            )
        return user

    return _guard
