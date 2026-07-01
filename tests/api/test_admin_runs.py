"""Tests for admin job-oversight + audit-log endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.config import get_settings
from fold_at_scripps.main import create_app
from fold_at_scripps.models import (
    AllowedEmail,
    Artifact,
    Run,
    RunStatus,
    Tool,
    User,
    UserRole,
    UserStatus,
)
from fold_at_scripps.storage import get_storage

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _tmp_storage_root(tmp_path, monkeypatch):
    """Redirect storage_root to a tmp dir so real file staging never touches the repo.

    Mirrors ``tests/api/test_runs.py``: the download endpoint serves real files, so
    isolate them per test and clear the settings cache so both ``create_app()`` and
    ``get_storage()`` pick up the override.
    """
    monkeypatch.setenv("FOLD_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _seed_tool(session: AsyncSession) -> Tool:
    await sync_catalog(
        session,
        FakeToolSource(
            [
                ToolRecord(
                    name="alpha",
                    version="1.0.0",
                    category="embedding",
                    gpu_count=1,
                    default_timeout=600,
                    supports_batch=False,
                    description="a",
                    image_tag="alpha:1",
                    input_schema={"type": "object"},
                )
            ]
        ),
    )
    return await session.scalar(select(Tool).where(Tool.name == "alpha"))


async def _user(session: AsyncSession, email: str, *, role: UserRole = UserRole.USER) -> User:
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


async def _run(session: AsyncSession, user: User, tool: Tool, status: RunStatus) -> Run:
    run = Run(user_id=user.id, tool_id=tool.id, params={}, status=status)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def _login_admin(client: AsyncClient, session: AsyncSession) -> User:
    admin = await _user(session, "admin@scripps.edu", role=UserRole.ADMIN)
    await client.post("/auth/login", json={"email": admin.email, "password": "s3cret-pw"})
    return admin


async def test_admin_lists_all_users_runs(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    bob = await _user(db_session, "bob@scripps.edu")
    await _run(db_session, alice, tool, RunStatus.QUEUED)
    await _run(db_session, bob, tool, RunStatus.SUCCEEDED)
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.get("/admin/runs")
        assert resp.status_code == 200
        emails = {r["user"]["email"] for r in resp.json()}
        assert {"alice@scripps.edu", "bob@scripps.edu"} <= emails


async def test_admin_filters_runs_by_status(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    await _run(db_session, alice, tool, RunStatus.QUEUED)
    await _run(db_session, alice, tool, RunStatus.SUCCEEDED)
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.get("/admin/runs", params={"status": "queued"})
        assert [r["status"] for r in resp.json()] == ["queued"]


async def test_admin_cancels_queued_run_of_another_user(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.QUEUED)
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.post(f"/admin/runs/{run.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "canceled"


async def test_admin_cancel_running_run_409(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.RUNNING)
    async with _client() as client:
        await _login_admin(client, db_session)
        assert (await client.post(f"/admin/runs/{run.id}/cancel")).status_code == 409


async def test_admin_cancel_unknown_run_404(db_session: AsyncSession):
    async with _client() as client:
        await _login_admin(client, db_session)
        assert (await client.post(f"/admin/runs/{uuid.uuid4()}/cancel")).status_code == 404


async def test_admin_downloads_another_users_artifact(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.SUCCEEDED)
    storage = get_storage()
    target = storage.outputs_dir(run.id) / "raw/result.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"HELLO")
    db_session.add(
        Artifact(
            run_id=run.id,
            name="result.txt",
            path="raw/result.txt",
            content_type="text/plain",
            size_bytes=5,
        )
    )
    await db_session.commit()
    async with _client() as client:
        await _login_admin(client, db_session)
        resp = await client.get(f"/admin/runs/{run.id}/artifacts/raw/result.txt")
        assert resp.status_code == 200
        assert resp.content == b"HELLO"


async def test_admin_download_unknown_artifact_404(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.SUCCEEDED)
    async with _client() as client:
        await _login_admin(client, db_session)
        assert (await client.get(f"/admin/runs/{run.id}/artifacts/nope.txt")).status_code == 404


async def test_audit_log_lists_admin_actions(db_session: AsyncSession):
    tool = await _seed_tool(db_session)
    alice = await _user(db_session, "alice@scripps.edu")
    run = await _run(db_session, alice, tool, RunStatus.QUEUED)
    async with _client() as client:
        await _login_admin(client, db_session)
        await client.post(f"/admin/runs/{run.id}/cancel")
        resp = await client.get("/admin/audit-logs")
        assert resp.status_code == 200
        assert any(e["action"] == "run.cancel" for e in resp.json())
