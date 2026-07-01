"""Admin job oversight: list, inspect, and cancel any user's runs."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fold_at_scripps.audit import record_audit
from fold_at_scripps.models import Run, RunStatus, User
from fold_at_scripps.runs.service import RunNotCancelable, RunNotFound


async def admin_list_runs(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    status: RunStatus | None = None,
) -> list[Run]:
    """Return all runs (optionally filtered by user/status), newest first."""
    stmt = select(Run).options(selectinload(Run.tool), selectinload(Run.user))
    if user_id is not None:
        stmt = stmt.where(Run.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    stmt = stmt.order_by(Run.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def admin_get_run(session: AsyncSession, run_id: uuid.UUID) -> Run | None:
    """Return any run by id with tool, user, and artifacts loaded, or None."""
    stmt = (
        select(Run)
        .where(Run.id == run_id)
        .options(selectinload(Run.tool), selectinload(Run.user), selectinload(Run.artifacts))
    )
    return await session.scalar(stmt)


async def admin_cancel_run(session: AsyncSession, *, actor: User, run_id: uuid.UUID) -> Run:
    """Cancel any user's queued run, audit it, and return the reloaded run.

    Raises:
        RunNotFound: no such run.
        RunNotCancelable: the run exists but is not QUEUED.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise RunNotFound(f"Run {run_id} not found")
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == RunStatus.QUEUED)
        .values(status=RunStatus.CANCELED)
    )
    if result.rowcount == 0:
        await session.rollback()
        raise RunNotCancelable("Only queued runs can be canceled")
    await record_audit(
        session,
        actor=actor,
        action="run.cancel",
        target_type="run",
        target_id=str(run_id),
    )
    await session.commit()
    reloaded = await admin_get_run(session, run_id)
    assert reloaded is not None  # just canceled it in this transaction
    return reloaded
