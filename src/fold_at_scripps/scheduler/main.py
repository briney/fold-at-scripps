"""Entry point that wires and runs the scheduler as a host process."""

from __future__ import annotations

import asyncio
import logging

from fold_at_scripps.autobio_executor import AutobioExecutor
from fold_at_scripps.config import get_settings
from fold_at_scripps.db import get_engine, get_sessionmaker
from fold_at_scripps.logging_config import configure_logging
from fold_at_scripps.scheduler.locking import acquire_scheduler_lock
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.scheduler.recovery import fail_orphaned_runs
from fold_at_scripps.scheduler.service import Scheduler
from fold_at_scripps.storage import get_storage

logger = logging.getLogger(__name__)


def build_scheduler() -> Scheduler:
    """Construct a Scheduler from application settings and the real components.

    SINGLE-PROCESS INVARIANT: GPU allocation lives entirely in the per-process
    in-memory GpuPool.  Two ``fold-scheduler`` processes running on the same node
    would each believe all GPUs are free and could co-assign the same GPU to
    concurrent runs.  Exactly one scheduler process must run per node.  Enforcing
    this guarantee (e.g. via an advisory lock or leader election) is deferred to
    the deployment plan.
    """
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
    """Enforce single-scheduler, recover orphaned runs, then poll forever.

    The single-process GPU-owner invariant described in ``build_scheduler`` is
    enforced here by taking a Postgres advisory lock on a dedicated connection
    before doing any work.  The connection is held open for the process lifetime
    so the lock persists; if another scheduler already holds it, this process
    exits with a non-zero status.
    """
    configure_logging(get_settings().log_level)
    lock_conn = await acquire_scheduler_lock(get_engine())
    if lock_conn is None:
        logger.error("Another fold-scheduler holds the advisory lock; exiting.")
        raise SystemExit(1)
    try:
        async with get_sessionmaker()() as session:
            await fail_orphaned_runs(session)
        await build_scheduler().run_forever()
    finally:
        await lock_conn.close()


def main() -> None:
    """Console-script entry point for the scheduler daemon."""
    configure_logging(get_settings().log_level)
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
