"""Tests for admin user-management endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, AuditLog, User, UserRole, UserStatus

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _make_user(session: AsyncSession, email: str, *, role: UserRole = UserRole.USER) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        hashed_password=hash_password("s3cret-pw"),
        role=role,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.add(AllowedEmail(email=email))
    await session.commit()
    await session.refresh(user)
    return user


async def _login_admin(client: AsyncClient, session: AsyncSession) -> User:
    admin = await _make_user(session, "admin@scripps.edu", role=UserRole.ADMIN)
    await client.post("/auth/login", json={"email": admin.email, "password": "s3cret-pw"})
    return admin


async def _login_regular(client: AsyncClient, session: AsyncSession) -> User:
    user = await _make_user(session, "reg@scripps.edu")
    await client.post("/auth/login", json={"email": user.email, "password": "s3cret-pw"})
    return user


async def test_list_users_requires_admin(db_session: AsyncSession):
    async with _client() as client:
        assert (await client.get("/admin/users")).status_code == 401
        await _login_regular(client, db_session)
        assert (await client.get("/admin/users")).status_code == 403


async def test_admin_lists_users(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        await _make_user(db_session, "bob@scripps.edu")
        resp = await client.get("/admin/users")
        assert resp.status_code == 200
        assert {u["email"] for u in resp.json()} == {"admin@scripps.edu", "bob@scripps.edu"}


async def test_admin_updates_user_and_audits(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        target = await _make_user(db_session, "bob@scripps.edu")
        resp = await client.patch(
            f"/admin/users/{target.id}",
            json={"tier": "power", "status": "disabled", "max_concurrent_runs_override": 20},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tier"] == "power" and body["status"] == "disabled"
        assert body["max_concurrent_runs_override"] == 20
        audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.update"))
        assert audit is not None and audit.target_id == str(target.id)


async def test_update_unknown_user_404(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.patch(f"/admin/users/{uuid.uuid4()}", json={"tier": "power"})
        assert resp.status_code == 404
