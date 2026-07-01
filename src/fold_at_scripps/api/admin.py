"""Admin API endpoints (all gated by require_admin)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.admin.access import (
    AllowedEmailNotFound,
    EmailAlreadyAllowed,
    add_allowed_email,
    list_allowed_emails,
    remove_allowed_email,
)
from fold_at_scripps.admin.catalog import ToolNotFound, set_tool_enabled, trigger_sync
from fold_at_scripps.admin.passwords import create_password_reset
from fold_at_scripps.admin.settings import update_settings
from fold_at_scripps.admin.users import UserNotFound, get_user, list_users, update_user
from fold_at_scripps.auth.dependencies import require_admin
from fold_at_scripps.catalog.autobio_source import get_tool_source
from fold_at_scripps.catalog.service import list_all_tools
from fold_at_scripps.catalog.sources import ToolSource
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User
from fold_at_scripps.schemas.admin import (
    AdminUserRead,
    AdminUserUpdate,
    AllowedEmailCreate,
    AllowedEmailRead,
    CatalogSyncResult,
    PasswordResetResponse,
    SystemSettingsRead,
    SystemSettingsUpdate,
    ToolAdminRead,
    ToolEnabledUpdate,
)
from fold_at_scripps.system_settings import get_system_settings

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


@router.get("/allowed-emails", response_model=list[AllowedEmailRead])
async def admin_list_allowed_emails(session: AsyncSession = Depends(get_session)) -> Any:
    """List allowlisted emails."""
    return await list_allowed_emails(session)


@router.post(
    "/allowed-emails", response_model=AllowedEmailRead, status_code=status.HTTP_201_CREATED
)
async def admin_add_allowed_email(
    payload: AllowedEmailCreate,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
) -> Any:
    """Add an email to the registration allowlist."""
    try:
        return await add_allowed_email(session, actor=actor, email=payload.email)
    except EmailAlreadyAllowed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/allowed-emails/{allowed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_remove_allowed_email(
    allowed_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
) -> None:
    """Remove an email from the registration allowlist."""
    try:
        await remove_allowed_email(session, actor=actor, allowed_id=allowed_id)
    except AllowedEmailNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/users/{user_id}/password-reset",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_password_reset(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
) -> Any:
    """Create a one-time password-reset token for a user."""
    try:
        token, row = await create_password_reset(session, actor=actor, user_id=user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PasswordResetResponse(token=token, expires_at=row.expires_at)


@router.get("/settings", response_model=SystemSettingsRead)
async def admin_get_settings(session: AsyncSession = Depends(get_session)) -> Any:
    """Return the current operational settings."""
    return await get_system_settings(session)


@router.patch("/settings", response_model=SystemSettingsRead)
async def admin_update_settings(
    payload: SystemSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
) -> Any:
    """Update operational settings (maintenance mode, quota caps)."""
    return await update_settings(
        session, actor=actor, changes=payload.model_dump(exclude_unset=True)
    )


@router.get("/tools", response_model=list[ToolAdminRead])
async def admin_list_tools(session: AsyncSession = Depends(get_session)) -> Any:
    """List all tools, including disabled ones."""
    return await list_all_tools(session)


@router.patch("/tools/{tool_id}", response_model=ToolAdminRead)
async def admin_set_tool_enabled(
    tool_id: uuid.UUID,
    payload: ToolEnabledUpdate,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
) -> Any:
    """Enable or disable a tool."""
    try:
        return await set_tool_enabled(
            session, actor=actor, tool_id=tool_id, enabled=payload.enabled
        )
    except ToolNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/catalog/sync", response_model=CatalogSyncResult)
async def admin_sync_catalog(
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_admin),
    source: ToolSource = Depends(get_tool_source),
) -> Any:
    """Trigger a catalog sync from the configured tool source."""
    return await trigger_sync(session, actor=actor, source=source)
