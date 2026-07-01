"""Tests for run query and lifecycle operations."""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.runs.service import (
    RunNotCancelable,
    RunNotFound,
    cancel_run,
    get_run,
    list_runs,
    soft_delete_run,
)

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession, email: str = "l@scripps.edu") -> User:
    user = User(email=email, display_name="L", hashed_password="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema={})
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def _run(session: AsyncSession, user: User, tool: Tool, **kw) -> Run:
    kw.setdefault("status", RunStatus.QUEUED)
    run = Run(user_id=user.id, tool_id=tool.id, params={}, **kw)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_list_excludes_hidden_and_other_users(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    other = await _user(db_session, email="other@scripps.edu")
    tool = await _tool(db_session)
    await _run(db_session, user, tool)
    await _run(db_session, user, tool, hidden_at=datetime.datetime.now(datetime.UTC))
    await _run(db_session, other, tool)
    runs = await list_runs(db_session, user)
    assert len(runs) == 1
    assert runs[0].tool.name == "t"  # eager-loaded


async def test_get_run_ownership(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    other = await _user(db_session, email="other@scripps.edu")
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool)
    assert (await get_run(db_session, user, run.id)) is not None
    assert (await get_run(db_session, other, run.id)) is None


async def test_cancel_queued_run(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool)
    cancelled = await cancel_run(db_session, user, run.id)
    assert cancelled.status is RunStatus.CANCELED


async def test_cancel_non_queued_raises(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool, status=RunStatus.RUNNING)
    with pytest.raises(RunNotCancelable):
        await cancel_run(db_session, user, run.id)


async def test_cancel_unknown_run_raises_not_found(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    with pytest.raises(RunNotFound):
        await cancel_run(db_session, user, uuid.uuid4())


async def test_soft_delete_hides_run(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    run = await _run(db_session, user, tool)
    await soft_delete_run(db_session, user, run.id)
    assert await list_runs(db_session, user) == []
