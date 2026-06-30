"""Catalog synchronization: upsert tools from a ToolSource."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.catalog.sources import ToolRecord, ToolSource
from fold_at_scripps.models import Tool


@dataclass
class SyncResult:
    """Summary of a catalog sync run."""

    added: int
    updated: int


def _apply(tool: Tool, record: ToolRecord) -> None:
    """Copy a record's metadata onto a Tool (never touches `enabled`)."""
    tool.category = record.category
    tool.gpu_count = record.gpu_count
    tool.input_schema = record.input_schema
    tool.description = record.description
    tool.image_tag = record.image_tag
    tool.default_timeout = record.default_timeout
    tool.supports_batch = record.supports_batch


async def sync_catalog(session: AsyncSession, source: ToolSource) -> SyncResult:
    """Upsert every tool from ``source`` into the catalog.

    Existing tools (matched by name + version) have their metadata refreshed but
    keep their admin-controlled ``enabled`` flag; new tools are created enabled.
    """
    records = await asyncio.to_thread(source.fetch_tools)
    added = 0
    updated = 0
    for record in records:
        stmt = select(Tool).where(Tool.name == record.name, Tool.version == record.version)
        existing = await session.scalar(stmt)
        if existing is None:
            tool = Tool(name=record.name, version=record.version, enabled=True)
            _apply(tool, record)
            session.add(tool)
            added += 1
        else:
            _apply(existing, record)
            updated += 1
    await session.commit()
    return SyncResult(added=added, updated=updated)


async def list_enabled_tools(session: AsyncSession, *, category: str | None = None) -> list[Tool]:
    """Return enabled tools, optionally filtered by category, ordered by name."""
    stmt = select(Tool).where(Tool.enabled.is_(True))
    if category is not None:
        stmt = stmt.where(Tool.category == category)
    stmt = stmt.order_by(Tool.name)
    return list((await session.execute(stmt)).scalars().all())


async def get_enabled_tool(session: AsyncSession, tool_id: uuid.UUID) -> Tool | None:
    """Return a single enabled tool by id, or None."""
    tool = await session.get(Tool, tool_id)
    if tool is None or not tool.enabled:
        return None
    return tool
