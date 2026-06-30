"""Catalog read endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.catalog.service import get_enabled_tool, list_enabled_tools
from fold_at_scripps.db import get_session
from fold_at_scripps.models import Tool, User
from fold_at_scripps.schemas.tools import ToolRead, ToolSummary

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolSummary])
async def list_tools(
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[Tool]:
    """List enabled tools, optionally filtered by category."""
    return await list_enabled_tools(session, category=category)


@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    tool_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> ToolRead:
    """Return a single enabled tool, including its input schema."""
    tool = await get_enabled_tool(session, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool
