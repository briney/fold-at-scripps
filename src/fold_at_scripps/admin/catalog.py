"""Admin catalog operations: enable/disable tools and trigger sync."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.audit import record_audit
from fold_at_scripps.catalog.service import SyncResult, sync_catalog
from fold_at_scripps.catalog.sources import ToolSource
from fold_at_scripps.models import Tool, User


class ToolNotFound(Exception):
    """Raised when no tool matches the given id."""


async def set_tool_enabled(
    session: AsyncSession, *, actor: User, tool_id: uuid.UUID, enabled: bool
) -> Tool:
    """Enable or disable a tool, audit it, and commit.

    Raises:
        ToolNotFound: no such tool.
    """
    tool = await session.get(Tool, tool_id)
    if tool is None:
        raise ToolNotFound(f"Tool {tool_id} not found")
    tool.enabled = enabled
    action = "catalog.tool_enabled" if enabled else "catalog.tool_disabled"
    await record_audit(
        session,
        actor=actor,
        action=action,
        target_type="tool",
        target_id=str(tool_id),
    )
    await session.commit()
    await session.refresh(tool)
    return tool


async def trigger_sync(session: AsyncSession, *, actor: User, source: ToolSource) -> SyncResult:
    """Sync the catalog from the given source and audit the event."""
    result = await sync_catalog(session, source)
    await record_audit(
        session,
        actor=actor,
        action="catalog.sync",
        target_type="catalog",
        details={"added": result.added, "updated": result.updated},
    )
    await session.commit()
    return result
