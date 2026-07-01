"""Accessor for the SystemSettings singleton (DB-backed operational config)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import SystemSettings

_SINGLETON_ID = 1


async def get_system_settings(session: AsyncSession) -> SystemSettings:
    """Return the SystemSettings row, creating it with defaults if it does not exist.

    Concurrent first-time callers may race to create the singleton; if this session's
    insert loses that race, only the nested insert is rolled back (via a SAVEPOINT) so
    the caller's own transaction and already-loaded objects are left intact.
    """
    settings = await session.get(SystemSettings, _SINGLETON_ID)
    if settings is not None:
        return settings
    try:
        async with session.begin_nested():
            settings = SystemSettings(id=_SINGLETON_ID)
            session.add(settings)
            await session.flush()
    except IntegrityError:
        # Another session created the singleton concurrently; use its row instead.
        settings = await session.get(SystemSettings, _SINGLETON_ID)
        if settings is None:  # pragma: no cover - defensive; row must exist post-race
            raise
    return settings
