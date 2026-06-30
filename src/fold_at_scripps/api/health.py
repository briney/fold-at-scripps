"""Health-check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def liveness() -> dict[str, str]:
    """Liveness probe — confirms the process is serving requests."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness probe — confirms the database is reachable."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
