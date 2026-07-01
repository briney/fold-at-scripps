"""Tests for the audit-log helper."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.audit import list_audit_logs, record_audit
from fold_at_scripps.models import User, UserRole, UserStatus

pytestmark = pytest.mark.integration


async def _actor(session: AsyncSession) -> User:
    user = User(
        email="admin@scripps.edu",
        display_name="Admin",
        hashed_password="x",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_record_audit_persists_row(db_session: AsyncSession):
    actor = await _actor(db_session)
    entry = await record_audit(
        db_session,
        actor=actor,
        action="user.update",
        target_type="user",
        target_id=str(actor.id),
        details={"tier": "power"},
    )
    await db_session.commit()
    assert entry.actor_id == actor.id
    logs = await list_audit_logs(db_session)
    assert [(e.action, e.details) for e in logs] == [("user.update", {"tier": "power"})]


async def test_record_audit_allows_null_actor(db_session: AsyncSession):
    await record_audit(db_session, actor=None, action="user.password_reset_redeemed")
    await db_session.commit()
    logs = await list_audit_logs(db_session)
    assert logs[0].actor_id is None
