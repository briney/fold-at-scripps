"""Per-user concurrency quota enforcement."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, SystemSettings, User, UserTier
from fold_at_scripps.system_settings import get_system_settings

_IN_FLIGHT = (RunStatus.QUEUED, RunStatus.RUNNING)


class QuotaExceeded(Exception):
    """Raised when a user is at their concurrent-run limit."""


def effective_concurrency_limit(user: User, settings: SystemSettings) -> int:
    """Return the user's concurrency cap: per-user override, else the tier default."""
    if user.max_concurrent_runs_override is not None:
        return user.max_concurrent_runs_override
    if user.tier is UserTier.POWER:
        return settings.power_max_concurrent_runs
    return settings.standard_max_concurrent_runs


async def count_in_flight_runs(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Count the user's queued or running runs."""
    stmt = (
        select(func.count())
        .select_from(Run)
        .where(Run.user_id == user_id, Run.status.in_(_IN_FLIGHT))
    )
    return await session.scalar(stmt) or 0


async def check_quota(session: AsyncSession, user: User) -> None:
    """Raise QuotaExceeded if the user is at or above their concurrency limit."""
    settings = await get_system_settings(session)
    limit = effective_concurrency_limit(user, settings)
    in_flight = await count_in_flight_runs(session, user.id)
    if in_flight >= limit:
        raise QuotaExceeded(f"Concurrency limit of {limit} reached")
