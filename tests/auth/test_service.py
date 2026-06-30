"""Tests for the registration service."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.service import (
    EmailAlreadyRegistered,
    RegistrationNotAllowed,
    register_user,
)
from fold_at_scripps.models import AllowedEmail, UserStatus

pytestmark = pytest.mark.integration


async def _allow(session: AsyncSession, email: str) -> None:
    session.add(AllowedEmail(email=email))
    await session.commit()


async def test_register_allowlisted_creates_pending_user(db_session: AsyncSession) -> None:
    await _allow(db_session, "new@scripps.edu")
    user = await register_user(
        db_session, email="new@scripps.edu", password="s3cret-pw", display_name="New User"
    )
    assert user.id is not None
    assert user.status is UserStatus.PENDING
    assert user.hashed_password != "s3cret-pw"


async def test_register_rejects_non_allowlisted_email(db_session: AsyncSession) -> None:
    with pytest.raises(RegistrationNotAllowed):
        await register_user(
            db_session, email="stranger@scripps.edu", password="s3cret-pw", display_name="X"
        )


async def test_register_rejects_duplicate_email(db_session: AsyncSession) -> None:
    await _allow(db_session, "dup@scripps.edu")
    await register_user(db_session, email="dup@scripps.edu", password="s3cret-pw", display_name="A")
    with pytest.raises(EmailAlreadyRegistered):
        await register_user(
            db_session, email="dup@scripps.edu", password="other-pw", display_name="B"
        )
