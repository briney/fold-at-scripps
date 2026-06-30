"""FastAPI dependencies for authentication."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.db import get_session
from fold_at_scripps.models import User, UserStatus

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
)


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    """Return the active user identified by the session cookie, or raise 401."""
    raw_id = request.session.get("user_id")
    if raw_id is None:
        raise _UNAUTHENTICATED
    try:
        user_id = uuid.UUID(raw_id)
    except (ValueError, TypeError) as exc:
        raise _UNAUTHENTICATED from exc
    user = await session.get(User, user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        raise _UNAUTHENTICATED
    return user
