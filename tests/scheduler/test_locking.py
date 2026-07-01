"""The scheduler advisory lock admits exactly one holder."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from fold_at_scripps.config import get_settings
from fold_at_scripps.scheduler.locking import acquire_scheduler_lock

pytestmark = pytest.mark.integration


async def test_only_one_holder():
    # NullPool: a session-level advisory lock is released only when the Postgres
    # session ends. With a pooling engine, `conn.close()` returns the connection
    # to the pool WITHOUT ending its session, so the lock would linger and make
    # the "re-acquire after release" assertion pool-order-dependent. NullPool
    # makes `close()` physically end the session, releasing the lock
    # deterministically. (Production holds one connection for the process
    # lifetime and never closes it, so the default engine is correct there.)
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        first = await acquire_scheduler_lock(engine)
        assert first is not None
        second = await acquire_scheduler_lock(engine)
        assert second is None  # already held
        await first.close()  # release
        third = await acquire_scheduler_lock(engine)
        assert third is not None  # re-acquirable after release
        await third.close()
    finally:
        await engine.dispose()
