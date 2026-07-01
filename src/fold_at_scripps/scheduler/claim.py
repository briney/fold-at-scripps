"""Atomically claim a runnable queued run and assign it GPUs."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool
from fold_at_scripps.scheduler.pool import GpuPool


async def claim_runnable_run(session: AsyncSession, pool: GpuPool) -> tuple[Run, list[int]] | None:
    """Claim the oldest queued run that fits the free GPU pool.

    Locks candidate rows with FOR UPDATE SKIP LOCKED, allocates GPUs for the first
    run whose tool needs no more than are free, transitions it to RUNNING with
    assigned GPUs and a start time, commits, and returns ``(run, gpu_ids)``.
    Returns None when no queued run fits.
    """
    stmt = (
        select(Run, Tool.gpu_count)
        .join(Tool, Run.tool_id == Tool.id)
        .where(Run.status == RunStatus.QUEUED)
        .order_by(Run.created_at)
        .with_for_update(skip_locked=True, of=Run)
    )
    rows = (await session.execute(stmt)).all()
    for run, gpu_count in rows:
        gpu_ids = pool.try_allocate(gpu_count)
        if gpu_ids is None:
            continue
        run.status = RunStatus.RUNNING
        run.assigned_gpu_ids = gpu_ids
        run.started_at = datetime.datetime.now(datetime.UTC)
        await session.commit()
        await session.refresh(run)
        return run, gpu_ids
    return None
