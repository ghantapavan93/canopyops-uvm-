"""Synthetic authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, verify_password
from app.models.domain import Tenant, User
from app.schemas import AuthUser, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def issue_token(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "bad_credentials", "message": "Invalid email or password"},
        )
    return TokenResponse(access_token=create_access_token(user), user=_to_auth(db, user))


@router.get("/me", response_model=AuthUser)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthUser:
    return _to_auth(db, user)


def _to_auth(db: Session, user: User) -> AuthUser:
    tenant = db.get(Tenant, user.tenant_id)
    return AuthUser(
        id=user.id, email=user.email, display_name=user.display_name, role=user.role,
        tenant_id=user.tenant_id, tenant_name=tenant.name if tenant else None,
    )
