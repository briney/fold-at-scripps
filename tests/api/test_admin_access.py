"""Tests for admin allowlist endpoints."""

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


async def test_add_list_remove_allowed_email(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        created = await client.post("/admin/allowed-emails", json={"email": "new@scripps.edu"})
        assert created.status_code == 201
        allowed_id = created.json()["id"]

        listed = await client.get("/admin/allowed-emails")
        assert "new@scripps.edu" in {a["email"] for a in listed.json()}

        deleted = await client.delete(f"/admin/allowed-emails/{allowed_id}")
        assert deleted.status_code == 204
        remaining = {a["email"] for a in (await client.get("/admin/allowed-emails")).json()}
        assert "new@scripps.edu" not in remaining


async def test_add_duplicate_email_409(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        await client.post("/admin/allowed-emails", json={"email": "dup@scripps.edu"})
        again = await client.post("/admin/allowed-emails", json={"email": "dup@scripps.edu"})
        assert again.status_code == 409


async def test_remove_unknown_allowed_email_404(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.delete(f"/admin/allowed-emails/{uuid.uuid4()}")
        assert resp.status_code == 404
