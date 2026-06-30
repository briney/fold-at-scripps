"""Tests for run submission."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import RunStatus, Tool, User, UserStatus
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import submit_run
from fold_at_scripps.runs.validation import InvalidParams
from fold_at_scripps.storage import LocalStorage

pytestmark = pytest.mark.integration

_SCHEMA = {
    "type": "object",
    "properties": {"num_sequences": {"type": "integer"}},
    "required": ["num_sequences"],
}


async def _user(session: AsyncSession) -> User:
    user = User(
        email="s@scripps.edu", display_name="S", hashed_password="x", status=UserStatus.ACTIVE
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema=_SCHEMA)
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
