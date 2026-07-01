"""Tests for the scheduler loop."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fold_at_scripps.executor import FakeExecutor
from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.scheduler.service import Scheduler
from fold_at_scripps.storage import LocalStorage
from fold_at_scripps.system_settings import get_system_settings

pytestmark = pytest.mark.integration


async def _seed_queued(session: AsyncSession, storage: LocalStorage, n: int) -> None:
    user = User(email="sch@scripps.edu", display_name="S", hashed_password="x")
    tool = Tool(name="t", version="1.0.0", category="c", input_schema={}, gpu_count=1)
    session.add_all([user, tool])
    await session.commit()
    for _ in range(n):
        session.add(Run(user_id=user.id, tool_id=tool.id, params={}, status=RunStatus.QUEUED))
    await session.commit()
    # Create per-run storage dirs (production does this in submit_run) so the
    # executor has an outputs directory to write into.
    for run in (await session.execute(select(Run))).scalars().all():
        storage.create_run_dir(run.id)


def _scheduler(db_session: AsyncSession, storage: LocalStorage, pool: GpuPool) -> Scheduler:
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    return Scheduler(
        sessionmaker=maker,
        executor=FakeExecutor(),
        storage=storage,
        gpu_pool=pool,
        poll_interval=0.01,
    )


async def test_run_once_dispatches_up_to_capacity(tmp_path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    await _seed_queued(db_session, storage, 3)
    pool = GpuPool([0, 1])  # capacity 2
    scheduler = _scheduler(db_session, storage, pool)

    await scheduler.run_once()
    await scheduler.drain()  # finish the 2 dispatched, free their GPUs
    assert pool.available == 2

    await scheduler.run_once()  # claim the 3rd
    await scheduler.drain()

    statuses = (await db_session.execute(select(Run.status))).scalars().all()
    assert all(s is RunStatus.SUCCEEDED for s in statuses)
    assert len(statuses) == 3


async def test_run_once_respects_maintenance_mode(tmp_path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    await _seed_queued(db_session, storage, 2)
    settings = await get_system_settings(db_session)
    settings.maintenance_mode = True
    await db_session.commit()
    scheduler = _scheduler(db_session, storage, GpuPool([0, 1]))

    await scheduler.run_once()
    await scheduler.drain()

    running = (
        (await db_session.execute(select(Run).where(Run.status != RunStatus.QUEUED)))
        .scalars()
        .all()
    )
    assert running == []  # nothing claimed while in maintenance
