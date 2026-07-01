"""Tests for run submission."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fold_at_scripps.config import get_settings
from fold_at_scripps.models import Run, RunStatus, Tool, User, UserStatus
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import InputFile, submit_run
from fold_at_scripps.runs.validation import InvalidParams
from fold_at_scripps.storage import LocalStorage

pytestmark = pytest.mark.integration

_SCHEMA = {
    "type": "object",
    "properties": {"num_sequences": {"type": "integer"}},
    "required": ["num_sequences"],
}


@pytest.fixture
def storage_tmp(tmp_path: Path) -> LocalStorage:
    """A LocalStorage instance rooted at a fresh temp directory."""
    return LocalStorage(tmp_path)


async def _user(session: AsyncSession) -> User:
    user = User(
        email="s@scripps.edu", display_name="S", hashed_password="x", status=UserStatus.ACTIVE
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession, input_schema: dict[str, Any] | None = None) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema=input_schema or _SCHEMA)
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def test_submit_creates_queued_run(tmp_path: Path, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    storage = LocalStorage(tmp_path)
    run = await submit_run(
        db_session, user=user, tool=tool, params={"num_sequences": 8}, storage=storage
    )
    assert run.status is RunStatus.QUEUED
    assert run.user_id == user.id
    assert run.tool_id == tool.id
    assert storage.config_path(run.id).exists()


async def test_submit_rejects_invalid_params(tmp_path: Path, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    with pytest.raises(InvalidParams):
        await submit_run(
            db_session, user=user, tool=tool, params={}, storage=LocalStorage(tmp_path)
        )
    count = await db_session.scalar(select(func.count()).select_from(Run))
    assert count == 0


async def test_submit_enforces_quota(tmp_path: Path, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    user.max_concurrent_runs_override = 1
    await db_session.commit()
    tool = await _tool(db_session)
    storage = LocalStorage(tmp_path)
    await submit_run(db_session, user=user, tool=tool, params={"num_sequences": 1}, storage=storage)
    with pytest.raises(QuotaExceeded):
        await submit_run(
            db_session, user=user, tool=tool, params={"num_sequences": 2}, storage=storage
        )
    count = await db_session.scalar(select(func.count()).select_from(Run))
    assert count == 1


async def test_submit_stages_inputs_and_resolves_config_paths(
    db_session: AsyncSession, storage_tmp: LocalStorage
) -> None:
    user = await _user(db_session)
    tool = await _tool(
        db_session,
        input_schema={
            "type": "object",
            "properties": {"structure_path": {"type": "string", "format": "path"}},
            "required": ["structure_path"],
        },
    )

    run = await submit_run(
        db_session,
        user=user,
        tool=tool,
        params={"structure_path": "backbone.pdb"},
        storage=storage_tmp,
        inputs=[InputFile(filename="backbone.pdb", content=b"ATOM  ...")],
    )

    # File staged to inputs/.
    assert storage_tmp.input_path(run.id, "backbone.pdb").read_bytes() == b"ATOM  ..."
    # Run.params keeps the user-facing filename.
    assert run.params["structure_path"] == "backbone.pdb"
    # config.json resolves the path field to the absolute staged path.
    config = json.loads(storage_tmp.config_path(run.id).read_text())
    assert config["structure_path"] == str(storage_tmp.input_path(run.id, "backbone.pdb"))


async def test_submit_quota_atomic_under_concurrency(
    db_session: AsyncSession, storage_tmp: LocalStorage
) -> None:
    user = await _user(db_session)
    user.max_concurrent_runs_override = 1
    tool = await _tool(db_session, input_schema={"type": "object"})
    await db_session.commit()
    user_id, tool_id = user.id, tool.id

    # A second engine to the same database gives the two attempts independent
    # connections/transactions that genuinely contend on the user row lock.
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _attempt() -> str:
        async with maker() as s:
            u = await s.get(User, user_id)
            t = await s.get(Tool, tool_id)
            try:
                await submit_run(s, user=u, tool=t, params={}, storage=storage_tmp)
                return "ok"
            except QuotaExceeded:
                return "quota"

    try:
        results = await asyncio.gather(_attempt(), _attempt())
    finally:
        await engine.dispose()

    assert sorted(results) == ["ok", "quota"]  # exactly one succeeded; GREEN is deterministic
    count = await db_session.scalar(
        select(func.count()).select_from(Run).where(Run.user_id == user_id)
    )
    assert count == 1
