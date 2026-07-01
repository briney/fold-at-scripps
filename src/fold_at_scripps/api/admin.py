"""Admin API endpoints (all gated by require_admin)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.admin.users import UserNotFound, get_user, list_users, update_user
from fold_at_scripps.auth.dependencies import require_admin
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User
from fold_at_scripps.schemas.admin import AdminUserRead, AdminUserUpdate

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[AdminUserRead])
async def admin_list_users(session: AsyncSession = Depends(get_session)) -> Any:
    """List all user accounts."""
    return await list_users(session)


@router.get("/users/{user_id}", response_model=AdminUserRead)
async def admin_get_user(user_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Any:
    """Return one user account."""
    try:
        return await get_user(session, user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
) -> Any:
    """Update a user's status, tier, and/or quota override."""
    try:
        return await update_user(
            session, actor=actor, user_id=user_id, changes=payload.model_dump(exclude_unset=True)
        )
    except UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
