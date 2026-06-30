"""Tests for AllowedEmail and PasswordResetToken models."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import AllowedEmail, PasswordResetToken, User

pytestmark = pytest.mark.integration


async def test_allowed_email_unique(db_session: AsyncSession) -> None:
    db_session.add(AllowedEmail(email="ok@scripps.edu"))
    await db_session.commit()
    db_session.add(AllowedEmail(email="ok@scripps.edu"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_password_reset_token_cascades_with_user(db_session: AsyncSession) -> None:
    user = User(email="u@scripps.edu", display_name="U", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    token = PasswordResetToken(
        user_id=user.id,
        token_hash="hash123",
        expires_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
    )
    db_session.add(token)
    await db_session.commit()
    fetched_user = await db_session.get(User, user.id)
    await db_session.delete(fetched_user)
    await db_session.commit()
    remaining = (
        await db_session.execute(select(func.count()).select_from(PasswordResetToken))
    ).scalar_one()
    assert remaining == 0
