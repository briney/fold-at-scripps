"""Entry point that wires and runs the scheduler as a host process."""

from __future__ import annotations

import asyncio

from fold_at_scripps.autobio_executor import AutobioExecutor
from fold_at_scripps.config import get_settings
from fold_at_scripps.db import get_sessionmaker
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.scheduler.recovery import fail_orphaned_runs
from fold_at_scripps.scheduler.service import Scheduler
from fold_at_scripps.storage import get_storage


def build_scheduler() -> Scheduler:
    """Construct a Scheduler from application settings and the real components."""
    settings = get_settings()
    pool = GpuPool(list(range(settings.gpu_count)))
    return Scheduler(
        sessionmaker=get_sessionmaker(),
        executor=AutobioExecutor(),
        storage=get_storage(),
        gpu_pool=pool,
        poll_interval=settings.scheduler_poll_interval,
    )


async def run_scheduler() -> None:
    """Recover orphaned runs, then poll forever."""
    async with get_sessionmaker()() as session:
        await fail_orphaned_runs(session)
    await build_scheduler().run_forever()


def main() -> None:
    """Console-script entry point for the scheduler daemon."""
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
