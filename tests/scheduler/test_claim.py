"""Tests for claiming runnable queued runs."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.scheduler.claim import claim_runnable_run
from fold_at_scripps.scheduler.pool import GpuPool

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession) -> User:
    user = User(email="c@scripps.edu", display_name="C", hashed_password="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession, *, gpu_count: int = 1) -> Tool:
    tool = Tool(
        name=f"t{gpu_count}", version="1.0.0", category="c", input_schema={}, gpu_count=gpu_count
    )
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def _queue(session: AsyncSession, user: User, tool: Tool, when: int) -> Run:
    run = Run(
        user_id=user.id,
        tool_id=tool.id,
        params={},
        status=RunStatus.QUEUED,
        created_at=datetime.datetime(2026, 1, 1, 0, when, tzinfo=datetime.UTC),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def test_claim_transitions_oldest_fitting_run(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session, gpu_count=1)
    first = await _queue(db_session, user, tool, when=1)
    await _queue(db_session, user, tool, when=2)
    pool = GpuPool([0, 1])
    claimed = await claim_runnable_run(db_session, pool)
    assert claimed is not None
    run, gpu_ids = claimed
    assert run.id == first.id
    assert run.status is RunStatus.RUNNING
    assert run.assigned_gpu_ids == gpu_ids == [0]
    assert run.started_at is not None
    assert pool.available == 1


async def test_claim_returns_none_when_nothing_fits(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session, gpu_count=4)
    await _queue(db_session, user, tool, when=1)
    pool = GpuPool([0, 1])  # only 2 free, run needs 4
    assert await claim_runnable_run(db_session, pool) is None


async def test_claim_returns_none_when_no_queued(db_session: AsyncSession) -> None:
    pool = GpuPool([0, 1])
    assert await claim_runnable_run(db_session, pool) is None


async def test_claim_releases_gpus_when_commit_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GPU pool must not leak when the commit that persists a claim fails."""
    user = await _user(db_session)
    tool = await _tool(db_session, gpu_count=1)
    await _queue(db_session, user, tool, when=1)

    pool = GpuPool([0, 1])
    original_available = pool.available

    # Patch commit so it raises after GPUs have been tentatively allocated.
    monkeypatch.setattr(db_session, "commit", AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        await claim_runnable_run(db_session, pool)

    # GPUs must be fully restored.
    assert pool.available == original_available

    # Roll back so we can re-query the run.
    await db_session.rollback()

    # The run must still be QUEUED (not left RUNNING).
    run = (await db_session.execute(select(Run))).scalars().first()
    assert run is not None
    assert run.status is RunStatus.QUEUED
