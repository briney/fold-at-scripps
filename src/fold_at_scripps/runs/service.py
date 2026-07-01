"""Run lifecycle service (transport-agnostic)."""

from __future__ import annotations

import asyncio
import datetime
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fold_at_scripps.executor import ExecutionRequest, Executor
from fold_at_scripps.models import Artifact, Run, RunStatus, Tool, User
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


class InvalidRunState(Exception):
    """Raised when a run is not in the expected state for an operation."""


async def execute_run(session: AsyncSession, run: Run, executor: Executor, storage: Storage) -> Run:
    """Execute a RUNNING run via the executor and record its outcome.

    The caller (scheduler) is responsible for the QUEUED -> RUNNING transition and
    for assigning GPUs. If the executor raises, the run is marked FAILED rather
    than left RUNNING.
    """
    if run.status is not RunStatus.RUNNING:
        raise InvalidRunState(f"execute_run requires a RUNNING run, got {run.status}")

    tool = await session.get(Tool, run.tool_id)
    if tool is None:  # pragma: no cover - referential integrity guarantees this
        raise ValueError(f"Run {run.id} references missing tool {run.tool_id}")

    request = ExecutionRequest(
        tool_name=tool.name,
        tool_version=tool.version,
        image_tag=tool.image_tag,
        config_path=storage.config_path(run.id),
        outputs_dir=storage.outputs_dir(run.id),
        gpu_ids=run.assigned_gpu_ids or [],
        timeout=tool.default_timeout,
    )
    try:
        result = await asyncio.to_thread(executor.execute, request)
    except Exception as exc:  # execution boundary: never leave a run RUNNING
        run.status = RunStatus.FAILED
        run.error = f"executor error: {exc}"
        run.finished_at = datetime.datetime.now(datetime.UTC)
        await session.commit()
        await session.refresh(run)
        return run

    run.finished_at = datetime.datetime.now(datetime.UTC)
    run.wall_time_seconds = result.wall_time_seconds
    run.gpu_seconds = result.gpu_seconds
    if result.succeeded:
        for stored in storage.list_outputs(run.id):
            session.add(
                Artifact(
                    run_id=run.id,
                    name=stored.name,
                    path=stored.relative_path,
                    content_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                )
            )
        run.status = RunStatus.SUCCEEDED
    else:
        run.status = RunStatus.FAILED
        run.error = result.error
    await session.commit()
    await session.refresh(run)
    return run
