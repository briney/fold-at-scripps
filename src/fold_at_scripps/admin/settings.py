"""Admin editing of the SystemSettings singleton."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.audit import record_audit
from fold_at_scripps.models import SystemSettings, User
from fold_at_scripps.system_settings import get_system_settings

_UPDATABLE = (
    "maintenance_mode",
    "standard_max_concurrent_runs",
    "power_max_concurrent_runs",
)


async def update_settings(
    session: AsyncSession, *, actor: User, changes: Mapping[str, Any]
) -> SystemSettings:
    """Apply allowed changes to the settings singleton, audit them, and commit."""
    settings = await get_system_settings(session)
    applied: dict[str, Any] = {}
    for key in _UPDATABLE:
        if key in changes:
            setattr(settings, key, changes[key])
            applied[key] = changes[key]
    await record_audit(
        session,
        actor=actor,
        action="settings.update",
        target_type="system_settings",
        target_id="1",
        details=applied,
    )
    await session.commit()
    await session.refresh(settings)
    return settings
