"""Regression: a suspended user is locked out on their next request."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, User, UserStatus

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_disabled_user_locked_out_on_next_request(db_session: AsyncSession):
    db_session.add(AllowedEmail(email="u@scripps.edu"))
    await db_session.commit()
    async with _client() as client:
        await client.post(
            "/auth/register",
            json={"email": "u@scripps.edu", "password": "s3cret-pw", "display_name": "U"},
        )
        user = await db_session.scalar(select(User).where(User.email == "u@scripps.edu"))
        user.status = UserStatus.ACTIVE
        await db_session.commit()
        await client.post("/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"})
        assert (await client.get("/auth/me")).status_code == 200

        user.status = UserStatus.DISABLED
        await db_session.commit()
        assert (await client.get("/auth/me")).status_code == 401
