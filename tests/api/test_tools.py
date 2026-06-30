"""Tests for the catalog read API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, Tool, User, UserStatus

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _record(name: str, category: str = "inverse-folding") -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category=category,
        gpu_count=1,
        default_timeout=600,
        supports_batch=True,
        description=f"{name} description",
        image_tag=f"{name}:1.0.0",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
    )


async def _seed_tools(session: AsyncSession) -> None:
    await sync_catalog(
        session,
        FakeToolSource([_record("alpha"), _record("beta", category="embedding")]),
    )


async def _login(client: AsyncClient, session: AsyncSession) -> None:
    session.add(AllowedEmail(email="u@scripps.edu"))
    await session.commit()
    await client.post(
        "/auth/register",
        json={"email": "u@scripps.edu", "password": "s3cret-pw", "display_name": "U"},
    )
    user = await session.scalar(select(User).where(User.email == "u@scripps.edu"))
    assert user is not None
    user.status = UserStatus.ACTIVE
    await session.commit()
    await client.post("/auth/login", json={"email": "u@scripps.edu", "password": "s3cret-pw"})


async def test_tools_requires_auth(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    async with _client() as client:
        assert (await client.get("/tools")).status_code == 401


async def test_list_tools_returns_enabled(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get("/tools")
        assert resp.status_code == 200
        names = {t["name"] for t in resp.json()}
        assert names == {"alpha", "beta"}


async def test_list_tools_filters_category(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get("/tools", params={"category": "embedding"})
        assert [t["name"] for t in resp.json()] == ["beta"]


async def test_disabled_tool_excluded(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    tool = await db_session.scalar(select(Tool).where(Tool.name == "alpha"))
    assert tool is not None
    tool.enabled = False
    await db_session.commit()
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get("/tools")
        assert [t["name"] for t in resp.json()] == ["beta"]
        detail = await client.get(f"/tools/{tool.id}")
        assert detail.status_code == 404


async def test_tool_detail_includes_schema(db_session: AsyncSession) -> None:
    await _seed_tools(db_session)
    tool = await db_session.scalar(select(Tool).where(Tool.name == "alpha"))
    assert tool is not None
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.get(f"/tools/{tool.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "alpha"
        assert body["input_schema"]["type"] == "object"
