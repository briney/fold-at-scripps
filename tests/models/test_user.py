"""Tests for the User model."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import User, UserRole, UserStatus, UserTier

pytestmark = pytest.mark.integration


async def test_user_defaults(db_session: AsyncSession) -> None:
    user = User(email="a@scripps.edu", display_name="Researcher A", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    assert user.role is UserRole.USER
    assert user.tier is UserTier.STANDARD
    assert user.status is UserStatus.PENDING
    assert user.max_concurrent_runs_override is None
    assert user.created_at is not None


async def test_user_email_unique(db_session: AsyncSession) -> None:
    db_session.add(User(email="dup@scripps.edu", display_name="A", hashed_password="x"))
    await db_session.commit()
    db_session.add(User(email="dup@scripps.edu", display_name="B", hashed_password="y"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_role_round_trips_as_value(db_session: AsyncSession) -> None:
    db_session.add(
        User(
            email="admin@scripps.edu",
            display_name="Admin",
            hashed_password="x",
            role=UserRole.ADMIN,
        )
    )
    await db_session.commit()
    stmt = select(User).where(User.email == "admin@scripps.edu")
    fetched = (await db_session.execute(stmt)).scalar_one()
    assert fetched.role is UserRole.ADMIN
