"""Tests for AuditLog and SystemSettings models."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import AuditLog, SystemSettings

pytestmark = pytest.mark.integration


async def test_audit_log_allows_null_actor(db_session: AsyncSession) -> None:
    entry = AuditLog(action="system.startup", details={"note": "boot"})
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    assert entry.id is not None
    assert entry.actor_id is None
    assert entry.details == {"note": "boot"}


async def test_system_settings_default(db_session: AsyncSession) -> None:
    settings = SystemSettings()
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(settings)
    assert settings.id == 1
    assert settings.maintenance_mode is False


async def test_system_settings_rejects_second_row(db_session: AsyncSession) -> None:
    db_session.add(SystemSettings(id=1))
    await db_session.commit()
    db_session.add(SystemSettings(id=2))
    with pytest.raises(IntegrityError):
        await db_session.commit()
