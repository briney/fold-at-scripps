"""Tests for catalog synchronization."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.service import sync_catalog
from fold_at_scripps.catalog.sources import FakeToolSource, ToolRecord
from fold_at_scripps.models import Tool

pytestmark = pytest.mark.integration


def _record(
    name: str, *, version: str = "1.0.0", schema: dict[str, Any] | None = None
) -> ToolRecord:
    return ToolRecord(
        name=name,
        version=version,
        category="inverse-folding",
        gpu_count=1,
        default_timeout=600,
        supports_batch=True,
        description=f"{name} description",
        image_tag=f"{name}:{version}",
        input_schema=schema if schema is not None else {"type": "object"},
    )


async def test_sync_adds_new_tools(db_session: AsyncSession) -> None:
    source = FakeToolSource([_record("a"), _record("b")])
    result = await sync_catalog(db_session, source)
    assert result.added == 2
    assert result.updated == 0
    tools = (await db_session.execute(select(Tool))).scalars().all()
    assert {t.name for t in tools} == {"a", "b"}
    assert all(t.enabled is True for t in tools)


async def test_resync_updates_without_duplicates(db_session: AsyncSession) -> None:
    await sync_catalog(db_session, FakeToolSource([_record("a", schema={"v": 1})]))
    result = await sync_catalog(db_session, FakeToolSource([_record("a", schema={"v": 2})]))
    assert result.added == 0
    assert result.updated == 1
    tools = (await db_session.execute(select(Tool))).scalars().all()
    assert len(tools) == 1
    assert tools[0].input_schema == {"v": 2}


async def test_sync_preserves_enabled_flag(db_session: AsyncSession) -> None:
    await sync_catalog(db_session, FakeToolSource([_record("a")]))
    tool = (await db_session.execute(select(Tool))).scalar_one()
    tool.enabled = False
    await db_session.commit()
    await sync_catalog(db_session, FakeToolSource([_record("a", schema={"v": 9})]))
    refreshed = (await db_session.execute(select(Tool))).scalar_one()
    assert refreshed.enabled is False
    assert refreshed.input_schema == {"v": 9}
