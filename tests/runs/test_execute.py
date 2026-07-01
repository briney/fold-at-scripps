"""Tests for executing a run via an executor."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.executor import ExecutionRequest, ExecutionResult, FakeExecutor
from fold_at_scripps.models import Artifact, Run, RunStatus, Tool, User
from fold_at_scripps.runs.service import InvalidRunState, execute_run
from fold_at_scripps.storage import LocalStorage

pytestmark = pytest.mark.integration


async def _running_run(session: AsyncSession, storage: LocalStorage) -> Run:
    user = User(email="e@scripps.edu", display_name="E", hashed_password="x")
    tool = Tool(
        name="t",
        version="1.0.0",
        category="c",
        input_schema={},
        image_tag="t:1.0.0",
        default_timeout=600,
    )
    session.add_all([user, tool])
    await session.commit()
    run = Run(
        user_id=user.id,
        tool_id=tool.id,
        params={},
        status=RunStatus.RUNNING,
        assigned_gpu_ids=[0],
        started_at=datetime.datetime.now(datetime.UTC),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    storage.create_run_dir(run.id)
    return run


async def test_execute_success_indexes_artifacts(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    result = await execute_run(db_session, run, FakeExecutor(), storage)
    assert result.status is RunStatus.SUCCEEDED
    assert result.finished_at is not None
    count = await db_session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.run_id == run.id)
    )
    assert count == 1


async def test_execute_failure_records_error(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    result = await execute_run(
        db_session, run, FakeExecutor(succeeded=False, error="kaboom", write_output=False), storage
    )
    assert result.status is RunStatus.FAILED
    assert result.error == "kaboom"


async def test_execute_requires_running(tmp_path: Path, db_session: AsyncSession) -> None:
    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    run.status = RunStatus.QUEUED
    await db_session.commit()
    with pytest.raises(InvalidRunState):
        await execute_run(db_session, run, FakeExecutor(), storage)


async def test_execute_marks_failed_when_executor_raises(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    class _BoomExecutor:
        def execute(self, request: ExecutionRequest) -> ExecutionResult:
            raise RuntimeError("executor crashed")

    storage = LocalStorage(tmp_path)
    run = await _running_run(db_session, storage)
    result = await execute_run(db_session, run, _BoomExecutor(), storage)
    assert result.status is RunStatus.FAILED
    assert "executor crashed" in (result.error or "")
