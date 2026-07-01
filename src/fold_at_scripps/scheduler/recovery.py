"""Startup recovery for runs orphaned by a scheduler crash/restart."""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus


async def fail_orphaned_runs(session: AsyncSession) -> int:
    """Mark all RUNNING runs FAILED (their execution was lost). Returns the count."""
    runs = (
        (await session.execute(select(Run).where(Run.status == RunStatus.RUNNING))).scalars().all()
    )
    for run in runs:
        run.status = RunStatus.FAILED
        run.error = "Run interrupted by scheduler restart"
        run.finished_at = datetime.datetime.now(datetime.UTC)
    await session.commit()
    return len(runs)
