"""Tests for admin catalog endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.catalog.autobio_source import get_tool_source
from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, Tool, User, UserRole, UserStatus

pytestmark = pytest.mark.integration


def _record(name: str) -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category="embedding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=False,
        description=f"{name}",
        image_tag=f"{name}:1.0.0",
        input_schema={"type": "object"},
    )


def _app_with_source(source):
    app = create_app()
    app.dependency_overrides[get_tool_source] = lambda: source
    return app


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


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


async def test_list_all_tools_includes_disabled(db_session: AsyncSession):
    await sync_catalog(db_session, FakeToolSource([_record("alpha"), _record("beta")]))
    tool = await db_session.scalar(select(Tool).where(Tool.name == "alpha"))
    tool.enabled = False
    await db_session.commit()
    async with _client(_app_with_source(FakeToolSource([]))) as client:
        await _login_admin(client, db_session)
        resp = await client.get("/admin/tools")
        names = {t["name"]: t["enabled"] for t in resp.json()}
        assert names == {"alpha": False, "beta": True}


async def test_toggle_tool_enabled_and_audit(db_session: AsyncSession):
    await sync_catalog(db_session, FakeToolSource([_record("alpha")]))
    tool = await db_session.scalar(select(Tool).where(Tool.name == "alpha"))
    async with _client(_app_with_source(FakeToolSource([]))) as client:
        await _login_admin(client, db_session)
        resp = await client.patch(f"/admin/tools/{tool.id}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


async def test_patch_unknown_tool_404(db_session: AsyncSession):
    async with _client(_app_with_source(FakeToolSource([]))) as client:
        await _login_admin(client, db_session)
        resp = await client.patch(f"/admin/tools/{uuid.uuid4()}", json={"enabled": False})
        assert resp.status_code == 404


async def test_sync_trigger_uses_injected_source(db_session: AsyncSession):
    async with _client(_app_with_source(FakeToolSource([_record("gamma")]))) as client:
        await _login_admin(client, db_session)
        resp = await client.post("/admin/catalog/sync")
        assert resp.status_code == 200
        assert resp.json()["added"] == 1
        assert await db_session.scalar(select(Tool).where(Tool.name == "gamma")) is not None
