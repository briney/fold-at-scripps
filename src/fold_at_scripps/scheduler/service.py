"""The scheduler loop: reap finished dispatches, then claim and dispatch runs."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from fold_at_scripps.executor import Executor
from fold_at_scripps.models import Run
from fold_at_scripps.runs.service import execute_run
from fold_at_scripps.scheduler.claim import claim_runnable_run
from fold_at_scripps.scheduler.pool import GpuPool
from fold_at_scripps.storage import Storage
from fold_at_scripps.system_settings import get_system_settings

logger = logging.getLogger(__name__)


class Scheduler:
    """Owns the GPU pool and drives queued runs through the executor."""

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker,
        executor: Executor,
        storage: Storage,
        gpu_pool: GpuPool,
        poll_interval: float,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._executor = executor
        self._storage = storage
        self._pool = gpu_pool
        self._poll_interval = poll_interval
        self._inflight: dict[uuid.UUID, tuple[asyncio.Task[None], list[int]]] = {}

    def _reap(self) -> None:
        """Release GPUs for finished dispatches."""
        for run_id, (task, gpu_ids) in list(self._inflight.items()):
            if task.done():
                if not task.cancelled() and task.exception() is not None:
                    logger.error("Dispatch for run %s failed", run_id, exc_info=task.exception())
                self._pool.release(gpu_ids)
                del self._inflight[run_id]

    async def _dispatch(self, run_id: uuid.UUID) -> None:
        """Execute a claimed (RUNNING) run in its own session."""
        async with self._sessionmaker() as session:
            run = await session.get(Run, run_id)
            if run is None:
                logger.warning("Claimed run %s no longer exists; skipping dispatch", run_id)
                return
            await execute_run(session, run, self._executor, self._storage)

    async def run_once(self) -> None:
        """One scheduling iteration: reap, then (unless in maintenance) claim+dispatch."""
        self._reap()
        async with self._sessionmaker() as session:
            settings = await get_system_settings(session)
            if settings.maintenance_mode:
                return
            while True:
                claimed = await claim_runnable_run(session, self._pool)
                if claimed is None:
                    break
                run, gpu_ids = claimed
                task = asyncio.create_task(self._dispatch(run.id))
                self._inflight[run.id] = (task, gpu_ids)

    async def drain(self) -> None:
        """Await all in-flight dispatches and reap them (graceful stop / tests)."""
        tasks = [task for task, _ in self._inflight.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._reap()

    async def run_forever(self) -> None:
        """Poll forever: schedule work, then sleep for the poll interval."""
        while True:
            await self.run_once()
            await asyncio.sleep(self._poll_interval)
