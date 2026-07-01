"""Tests for admin system-settings endpoints."""

from __future__ import annotations

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


async def _login_admin(client: AsyncClient, session: AsyncSession) -> User:
    admin = User(
        email="admin@scripps.edu",
        display_name="Admin",
        hashed_password=hash_password("s3cret-pw"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    session.add(admin)
    session.add(AllowedEmail(email=admin.email))
    await session.commit()
    await client.post("/auth/login", json={"email": admin.email, "password": "s3cret-pw"})
    return admin


async def test_get_settings_returns_defaults(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.get("/admin/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["maintenance_mode"] is False
        assert body["standard_max_concurrent_runs"] == 3
        assert body["power_max_concurrent_runs"] == 12


async def test_update_settings_and_audit(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.patch(
            "/admin/settings",
            json={"maintenance_mode": True, "standard_max_concurrent_runs": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["maintenance_mode"] is True
        assert body["standard_max_concurrent_runs"] == 5
        assert body["power_max_concurrent_runs"] == 12  # unchanged
        audit = await db_session.scalar(
            select(AuditLog).where(AuditLog.action == "settings.update")
        )
        assert audit is not None


async def test_settings_requires_admin(db_session: AsyncSession):
    async with _client() as client:
        assert (await client.get("/admin/settings")).status_code == 401
