"""Authentication endpoints: register, login, logout, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.admin.passwords import InvalidResetToken, redeem_password_reset
from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.auth.providers import IdentityProvider, get_identity_provider
from fold_at_scripps.auth.service import (
    EmailAlreadyRegistered,
    RegistrationNotAllowed,
    register_user,
)
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User, UserStatus
from fold_at_scripps.schemas.auth import (
    LoginRequest,
    PasswordResetRedeem,
    RegisterRequest,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_session)) -> User:
    """Register a new account (allowlist-gated; created pending)."""
    try:
        return await register_user(
            session,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )
    except RegistrationNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=UserRead)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> User:
    """Verify credentials, enforce active status, and start a session."""
    user = await provider.authenticate(session, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if user.status is not UserStatus.ACTIVE:
        detail = (
            "Account is pending approval"
            if user.status is UserStatus.PENDING
            else "Account is disabled"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    request.session["user_id"] = str(user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    """Clear the session."""
    request.session.clear()


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently-authenticated user."""
    return current_user


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetRedeem, session: AsyncSession = Depends(get_session)
) -> None:
    """Redeem a password-reset token and set a new password."""
    try:
        await redeem_password_reset(session, token=payload.token, new_password=payload.new_password)
    except InvalidResetToken as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
