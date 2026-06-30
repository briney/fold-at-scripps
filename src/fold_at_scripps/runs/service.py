"""Run lifecycle service (transport-agnostic)."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.runs.quota import check_quota
from fold_at_scripps.runs.validation import validate_params
from fold_at_scripps.storage import Storage


async def submit_run(
    session: AsyncSession,
    *,
    user: User,
    tool: Tool,
    params: dict[str, Any],
    storage: Storage,
) -> Run:
    """Validate params, enforce the quota, persist the config, and queue a run.

    Raises:
        InvalidParams: params do not satisfy the tool's input schema.
        QuotaExceeded: the user is at their concurrency limit.
    """
    validate_params(params, tool.input_schema)
    await check_quota(session, user)

    run = Run(user_id=user.id, tool_id=tool.id, params=params, status=RunStatus.QUEUED)
    session.add(run)
    await session.flush()  # assign run.id

    storage.create_run_dir(run.id)
    storage.write_config(run.id, params)
    run.output_dir = str(storage.run_root(run.id))

    await session.commit()
    await session.refresh(run)
    return run


class RunNotCancelable(Exception):
    """Raised when a run cannot be canceled from its current state."""


async def list_runs(session: AsyncSession, user: User) -> list[Run]:
    """Return the user's non-hidden runs, newest first, with tool eager-loaded."""
    stmt = (
        select(Run)
        .where(Run.user_id == user.id, Run.hidden_at.is_(None))
        .options(selectinload(Run.tool))
        .order_by(Run.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run | None:
    """Return the user's non-hidden run by id (tool + artifacts loaded), or None."""
    stmt = (
        select(Run)
        .where(Run.id == run_id, Run.user_id == user.id, Run.hidden_at.is_(None))
        .options(selectinload(Run.tool), selectinload(Run.artifacts))
    )
    return await session.scalar(stmt)


async def cancel_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run:
    """Cancel a queued run. Raises RunNotCancelable if it is not queued (or not found)."""
    run = await get_run(session, user, run_id)
    if run is None or run.status is not RunStatus.QUEUED:
        raise RunNotCancelable("Only queued runs can be canceled")
    run.status = RunStatus.CANCELED
    await session.commit()
    await session.refresh(run)
    return run


async def soft_delete_run(session: AsyncSession, user: User, run_id: uuid.UUID) -> Run | None:
    """Hide a run from the user's history (soft delete); return it, or None if not found."""
    run = await get_run(session, user, run_id)
    if run is None:
        return None
    run.hidden_at = datetime.datetime.now(datetime.UTC)
    await session.commit()
    await session.refresh(run)
    return run
