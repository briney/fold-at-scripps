"""End-to-end tests for the auth API."""

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


async def _allow(session: AsyncSession, email: str) -> None:
    session.add(AllowedEmail(email=email))
    await session.commit()


async def _register(client: AsyncClient, email: str = "u@scripps.edu") -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": "s3cret-pw", "display_name": "U"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


async def _activate(session: AsyncSession, email: str) -> None:
    user = await session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.status = UserStatus.ACTIVE
    await session.commit()


async def test_register_requires_allowlist(db_session: AsyncSession) -> None:
    async with _client() as client:
        resp = await client.post(
            "/auth/register",
            json={"email": "stranger@scripps.edu", "password": "s3cret-pw", "display_name": "X"},
        )
    assert resp.status_code == 403


async def test_login_pending_is_forbidden(db_session: AsyncSession) -> None:
    await _allow(db_session, "u@scripps.edu")
    async with _client() as client:
        await _register(client)
        resp = await client.post(
            "/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"}
        )
    assert resp.status_code == 403


async def test_login_wrong_password(db_session: AsyncSession) -> None:
    await _allow(db_session, "u@scripps.edu")
    async with _client() as client:
        await _register(client)
        await _activate(db_session, "u@scripps.edu")
        resp = await client.post("/auth/login", json={"email": "u@scripps.edu", "password": "nope"})
    assert resp.status_code == 401


async def test_full_login_me_logout_flow(db_session: AsyncSession) -> None:
    await _allow(db_session, "u@scripps.edu")
    async with _client() as client:
        await _register(client)
        await _activate(db_session, "u@scripps.edu")

        # Not authenticated yet.
        assert (await client.get("/auth/me")).status_code == 401

        login = await client.post(
            "/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"}
        )
        assert login.status_code == 200
        assert login.json()["email"] == "u@scripps.edu"

        me = await client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["status"] == "active"

        assert (await client.post("/auth/logout")).status_code == 204
        assert (await client.get("/auth/me")).status_code == 401
