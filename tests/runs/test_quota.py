"""Tests for quota enforcement."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import Run, RunStatus, Tool, User, UserTier
from fold_at_scripps.runs.quota import QuotaExceeded, check_quota, effective_concurrency_limit
from fold_at_scripps.system_settings import get_system_settings

pytestmark = pytest.mark.integration


async def _user(session: AsyncSession, *, tier: UserTier = UserTier.STANDARD) -> User:
    user = User(email="q@scripps.edu", display_name="Q", hashed_password="x", tier=tier)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _tool(session: AsyncSession) -> Tool:
    tool = Tool(name="t", version="1.0.0", category="c", input_schema={})
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


async def _add_runs(session: AsyncSession, user: User, tool: Tool, n: int) -> None:
    for _ in range(n):
        session.add(Run(user_id=user.id, tool_id=tool.id, params={}, status=RunStatus.QUEUED))
    await session.commit()


async def test_effective_limit_by_tier(db_session: AsyncSession) -> None:
    settings = await get_system_settings(db_session)
    standard = await _user(db_session)
    assert effective_concurrency_limit(standard, settings) == 3


async def test_effective_limit_override(db_session: AsyncSession) -> None:
    settings = await get_system_settings(db_session)
    user = await _user(db_session)
    user.max_concurrent_runs_override = 1
    assert effective_concurrency_limit(user, settings) == 1


async def test_check_quota_under_limit(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    await _add_runs(db_session, user, tool, 2)
    await check_quota(db_session, user)  # 2 < 3, no raise


async def test_check_quota_at_limit_raises(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    tool = await _tool(db_session)
    await _add_runs(db_session, user, tool, 3)
    with pytest.raises(QuotaExceeded):
        await check_quota(db_session, user)
