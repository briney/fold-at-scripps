"""Tests for the Run model."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User

pytestmark = pytest.mark.integration


async def _make_user_and_tool(session: AsyncSession) -> tuple[User, Tool]:
    user = User(email="r@scripps.edu", display_name="R", hashed_password="x")
    tool = Tool(name="proteinmpnn", version="1.0.0", category="inverse_folding", input_schema={})
    session.add_all([user, tool])
    await session.commit()
    await session.refresh(user)
    await session.refresh(tool)
    return user, tool


async def test_run_defaults_and_relationships(db_session: AsyncSession) -> None:
    user, tool = await _make_user_and_tool(db_session)
    run = Run(user_id=user.id, tool_id=tool.id, params={"num_sequences": 8})
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    assert run.id is not None
    assert run.status is RunStatus.QUEUED
    assert run.assigned_gpu_ids is None
    assert run.started_at is None
    assert run.hidden_at is None
    assert run.params == {"num_sequences": 8}
    assert run.user.email == "r@scripps.edu"
    assert run.tool.name == "proteinmpnn"


async def test_run_assigned_gpu_ids_array(db_session: AsyncSession) -> None:
    user, tool = await _make_user_and_tool(db_session)
    run = Run(
        user_id=user.id,
        tool_id=tool.id,
        params={},
        status=RunStatus.RUNNING,
        assigned_gpu_ids=[0, 3],
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    assert run.assigned_gpu_ids == [0, 3]
    assert run.status is RunStatus.RUNNING
