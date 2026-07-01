"""Postgres advisory lock enforcing a single active scheduler process."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Fixed 64-bit key ("fold-sched"); any constant works as long as it's stable.
_SCHEDULER_LOCK_KEY = 0x666F6C6473636864


async def acquire_scheduler_lock(engine: AsyncEngine) -> AsyncConnection | None:
    """Try to take the scheduler advisory lock on a dedicated connection.

    Returns the open connection (whose lifetime holds the lock — keep it open)
    on success, or None if another live scheduler already holds it. The lock
    releases automatically when the returned connection is closed or dropped.
    """
    conn = await engine.connect()
    try:
        result = await conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _SCHEDULER_LOCK_KEY}
        )
        acquired = bool(result.scalar())
    except Exception:
        await conn.close()
        raise
    if not acquired:
        await conn.close()
        return None
    return conn
