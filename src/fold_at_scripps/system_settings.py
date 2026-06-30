"""Accessor for the SystemSettings singleton (DB-backed operational config)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import SystemSettings

_SINGLETON_ID = 1


async def get_system_settings(session: AsyncSession) -> SystemSettings:
    """Return the SystemSettings row, creating it with defaults if it does not exist."""
    settings = await session.get(SystemSettings, _SINGLETON_ID)
    if settings is None:
        settings = SystemSettings(id=_SINGLETON_ID)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings
