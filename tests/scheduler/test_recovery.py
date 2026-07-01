"""Tests for orphaned-run crash recovery."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.scheduler.recovery import fail_orphaned_runs

pytestmark = pytest.mark.integration


async def _run(session: AsyncSession, status: RunStatus) -> Run:
    user = User(email=f"{status.value}@scripps.edu", display_name="U", hashed_password="x")
    tool = Tool(name=f"t-{status.value}", version="1.0.0", category="c", input_schema={})
    session.add_all([user, tool])
    await session.commit()
    run = Run(user_id=user.id, tool_id=tool.id, params={}, status=status)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_fail_orphaned_marks_running_failed(db_session: AsyncSession) -> None:
    running = await _run(db_session, RunStatus.RUNNING)
    queued = await _run(db_session, RunStatus.QUEUED)
    done = await _run(db_session, RunStatus.SUCCEEDED)
    count = await fail_orphaned_runs(db_session)
    assert count == 1
    await db_session.refresh(running)
    await db_session.refresh(queued)
    await db_session.refresh(done)
    assert running.status is RunStatus.FAILED
    assert running.error is not None
    assert running.finished_at is not None
    assert queued.status is RunStatus.QUEUED
    assert done.status is RunStatus.SUCCEEDED
