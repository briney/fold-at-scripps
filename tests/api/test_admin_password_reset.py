"""Tests for admin-initiated password reset + public redemption."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, User, UserRole, UserStatus

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _seed(session: AsyncSession, email: str, *, role: UserRole = UserRole.USER) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        hashed_password=hash_password("old-pw-123"),
        role=role,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.add(AllowedEmail(email=email))
    await session.commit()
    await session.refresh(user)
    return user


async def _login_admin(client: AsyncClient, session: AsyncSession) -> User:
    admin = await _seed(session, "admin@scripps.edu", role=UserRole.ADMIN)
    await client.post("/auth/login", json={"email": admin.email, "password": "old-pw-123"})
    return admin


async def test_admin_reset_then_user_redeems(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        target = await _seed(db_session, "bob@scripps.edu")
        created = await client.post(f"/admin/users/{target.id}/password-reset")
        assert created.status_code == 201
        token = created.json()["token"]
        assert token

    async with _client() as anon:
        redeemed = await anon.post(
            "/auth/reset-password", json={"token": token, "new_password": "brand-new-pw-9"}
        )
        assert redeemed.status_code == 204
        # New password works, old does not.
        ok = await anon.post(
            "/auth/login", json={"email": "bob@scripps.edu", "password": "brand-new-pw-9"}
        )
        assert ok.status_code == 200
        bad = await anon.post(
            "/auth/login", json={"email": "bob@scripps.edu", "password": "old-pw-123"}
        )
        assert bad.status_code == 401


async def test_redeem_invalid_token_400(db_session: AsyncSession):
    async with _client() as anon:
        resp = await anon.post(
            "/auth/reset-password", json={"token": "nope", "new_password": "brand-new-pw-9"}
        )
        assert resp.status_code == 400


async def test_reset_unknown_user_404(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.post(f"/admin/users/{uuid.uuid4()}/password-reset")
        assert resp.status_code == 404


async def test_reset_token_single_use(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        target = await _seed(db_session, "carol@scripps.edu")
        token = (await client.post(f"/admin/users/{target.id}/password-reset")).json()["token"]
    async with _client() as anon:
        first = await anon.post(
            "/auth/reset-password", json={"token": token, "new_password": "first-new-pw-1"}
        )
        assert first.status_code == 204
        second = await anon.post(
            "/auth/reset-password", json={"token": token, "new_password": "second-new-pw-2"}
        )
        assert second.status_code == 400
