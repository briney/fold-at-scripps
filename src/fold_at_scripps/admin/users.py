"""Admin user-management operations."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.audit import record_audit
from fold_at_scripps.models import User

_UPDATABLE = ("status", "tier", "max_concurrent_runs_override")


class UserNotFound(Exception):
    """Raised when no user matches the given id."""


async def list_users(session: AsyncSession) -> list[User]:
    """Return all users, ordered by email."""
    stmt = select(User).order_by(User.email)
    return list((await session.execute(stmt)).scalars().all())


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Return a user by id, or raise UserNotFound."""
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFound(f"User {user_id} not found")
    return user


async def update_user(
    session: AsyncSession, *, actor: User, user_id: uuid.UUID, changes: Mapping[str, Any]
) -> User:
    """Apply allowed field changes to a user, audit them, and commit.

    Raises:
        UserNotFound: no such user.
    """
    user = await get_user(session, user_id)
    applied: dict[str, Any] = {}
    for key in _UPDATABLE:
        if key in changes:
            setattr(user, key, changes[key])
            applied[key] = changes[key]
    await record_audit(
        session,
        actor=actor,
        action="user.update",
        target_type="user",
        target_id=str(user_id),
        details=applied,
    )
    await session.commit()
    await session.refresh(user)
    return user
