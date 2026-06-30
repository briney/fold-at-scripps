"""Run lifecycle service (transport-agnostic)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User
from fold_at_scripps.runs.quota import check_quota
from fold_at_scripps.runs.validation import validate_params
from fold_at_scripps.storage import Storage


async def submit_run(
    session: AsyncSession,
    *,
    user: User,
    tool: Tool,
    params: dict,
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
