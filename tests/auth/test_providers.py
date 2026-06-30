"""Tests for the local identity provider."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.auth.providers import LocalIdentityProvider
from fold_at_scripps.models import User, UserStatus

pytestmark = pytest.mark.integration


async def _add_user(session: AsyncSession, *, status: UserStatus = UserStatus.ACTIVE) -> User:
    user = User(
        email="r@scripps.edu",
        display_name="R",
        hashed_password=hash_password("good-pw"),
        status=status,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_authenticate_correct_credentials(db_session: AsyncSession) -> None:
    await _add_user(db_session)
    provider = LocalIdentityProvider()
    user = await provider.authenticate(db_session, "r@scripps.edu", "good-pw")
    assert user is not None
    assert user.email == "r@scripps.edu"


async def test_authenticate_wrong_password(db_session: AsyncSession) -> None:
    await _add_user(db_session)
    provider = LocalIdentityProvider()
    assert await provider.authenticate(db_session, "r@scripps.edu", "bad-pw") is None


async def test_authenticate_unknown_email(db_session: AsyncSession) -> None:
    provider = LocalIdentityProvider()
    assert await provider.authenticate(db_session, "nobody@scripps.edu", "x") is None


async def test_authenticate_returns_inactive_user(db_session: AsyncSession) -> None:
    # Provider verifies credentials only; status is enforced upstream.
    await _add_user(db_session, status=UserStatus.PENDING)
    provider = LocalIdentityProvider()
    user = await provider.authenticate(db_session, "r@scripps.edu", "good-pw")
    assert user is not None
    assert user.status is UserStatus.PENDING
