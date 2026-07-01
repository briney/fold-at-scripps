"""Tests for the user-facing runs API."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app
from fold_at_scripps.models import AllowedEmail, Tool, User, UserStatus

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _tmp_storage_root(tmp_path, monkeypatch):
    """Redirect storage_root to a tmp dir so real file staging never touches the repo.

    ``storage_root`` defaults to ``./data`` (CWD-relative); the submit and download
    endpoints stage/serve real files, so isolate them per test. Clear the settings
    cache after setting the env var so both create_app() and get_storage() pick it up.
    """
    monkeypatch.setenv("FOLD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _record(name: str = "antifold") -> ToolRecord:
    return ToolRecord(
        name=name,
        version="1.0.0",
        category="inverse-folding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=False,
        description="desc",
        image_tag=f"{name}:1.0.0",
        input_schema={
            "type": "object",
            "properties": {"structure_path": {"type": "string", "format": "path"}},
            "required": ["structure_path"],
        },
    )


async def _seed_tool(session: AsyncSession) -> Tool:
    await sync_catalog(session, FakeToolSource([_record()]))
    return await session.scalar(select(Tool).where(Tool.name == "antifold"))


async def _login(client: AsyncClient, session: AsyncSession, email: str = "u@scripps.edu") -> User:
    session.add(AllowedEmail(email=email))
    await session.commit()
    await client.post(
        "/auth/register", json={"email": email, "password": "s3cret-pw", "display_name": "U"}
    )
    user = await session.scalar(select(User).where(User.email == email))
    user.status = UserStatus.ACTIVE
    await session.commit()
    await client.post("/auth/login", json={"email": email, "password": "s3cret-pw"})
    return user


async def test_submit_requires_auth(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        resp = await client.post(
            "/runs",
            data={"tool_id": str(tool.id), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 401


async def test_submit_creates_queued_run_with_file(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.post(
            "/runs",
            data={"tool_id": str(tool.id), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "queued"
        assert body["tool"]["name"] == "antifold"
        assert body["params"]["structure_path"] == "b.pdb"
        assert body["artifacts"] == []


async def test_submit_invalid_params_returns_422(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        # structure_path is required; omit it.
        resp = await client.post("/runs", data={"tool_id": str(tool.id), "params": json.dumps({})})
        assert resp.status_code == 422


async def test_submit_bad_params_json_returns_422(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.post("/runs", data={"tool_id": str(tool.id), "params": "not-json"})
        assert resp.status_code == 422


async def test_submit_unknown_tool_returns_404(db_session: AsyncSession) -> None:
    await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        resp = await client.post(
            "/runs",
            data={"tool_id": str(uuid.uuid4()), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 404


async def test_submit_quota_exceeded_returns_429(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        user = await _login(client, db_session)
        user.max_concurrent_runs_override = 0
        await db_session.commit()
        resp = await client.post(
            "/runs",
            data={"tool_id": str(tool.id), "params": json.dumps({"structure_path": "b.pdb"})},
            files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
        )
        assert resp.status_code == 429


async def _submit(client: AsyncClient, tool_id: uuid.UUID) -> dict:
    resp = await client.post(
        "/runs",
        data={"tool_id": str(tool_id), "params": json.dumps({"structure_path": "b.pdb"})},
        files=[("files", ("b.pdb", b"ATOM", "chemical/x-pdb"))],
    )
    assert resp.status_code == 201
    return resp.json()


async def test_list_runs_returns_users_runs(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        await _submit(client, tool.id)
        resp = await client.get("/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["tool"]["name"] == "antifold"
        assert "artifacts" not in body[0]  # summary shape


async def test_get_run_detail_and_404(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        ok = await client.get(f"/runs/{run['id']}")
        assert ok.status_code == 200
        assert ok.json()["id"] == run["id"]
        missing = await client.get(f"/runs/{uuid.uuid4()}")
        assert missing.status_code == 404


async def test_cancel_endpoint_200_404_409(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        ok = await client.post(f"/runs/{run['id']}/cancel")
        assert ok.status_code == 200
        assert ok.json()["status"] == "canceled"
        again = await client.post(f"/runs/{run['id']}/cancel")  # now CANCELED, not queued
        assert again.status_code == 409
        missing = await client.post(f"/runs/{uuid.uuid4()}/cancel")
        assert missing.status_code == 404


async def test_delete_run_204_then_hidden(db_session: AsyncSession) -> None:
    tool = await _seed_tool(db_session)
    async with _client() as client:
        await _login(client, db_session)
        run = await _submit(client, tool.id)
        deleted = await client.delete(f"/runs/{run['id']}")
        assert deleted.status_code == 204
        assert (await client.get("/runs")).json() == []
        assert (await client.get(f"/runs/{run['id']}")).status_code == 404
        missing = await client.delete(f"/runs/{uuid.uuid4()}")
        assert missing.status_code == 404
