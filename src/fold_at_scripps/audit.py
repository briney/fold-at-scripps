"""Append-only audit log of administrative actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.models import AuditLog, User


async def record_audit(
    session: AsyncSession,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit entry to the session (flushes; the caller commits)."""
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_audit_logs(session: AsyncSession, *, limit: int = 100) -> list[AuditLog]:
    """Return the most recent audit entries, newest first."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())
