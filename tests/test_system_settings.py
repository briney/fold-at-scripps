"""Tests for the SystemSettings singleton accessor."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import SystemSettings
from fold_at_scripps.system_settings import get_system_settings

pytestmark = pytest.mark.integration


async def test_get_system_settings_creates_singleton(db_session: AsyncSession) -> None:
    settings = await get_system_settings(db_session)
    assert settings.id == 1
    assert settings.standard_max_concurrent_runs == 3
    count = await db_session.scalar(select(func.count()).select_from(SystemSettings))
    assert count == 1


async def test_get_system_settings_returns_existing(db_session: AsyncSession) -> None:
    first = await get_system_settings(db_session)
    first.power_max_concurrent_runs = 99
    await db_session.commit()
    second = await get_system_settings(db_session)
    assert second.power_max_concurrent_runs == 99
    count = await db_session.scalar(select(func.count()).select_from(SystemSettings))
    assert count == 1
