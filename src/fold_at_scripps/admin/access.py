"""Admin management of the registration allowlist."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.audit import record_audit
from fold_at_scripps.models import AllowedEmail, User


class EmailAlreadyAllowed(Exception):
    """Raised when an email is already on the allowlist."""


class AllowedEmailNotFound(Exception):
    """Raised when no allowlist entry matches the given id."""


async def list_allowed_emails(session: AsyncSession) -> list[AllowedEmail]:
    """Return all allowlist entries, ordered by email."""
    stmt = select(AllowedEmail).order_by(AllowedEmail.email)
    return list((await session.execute(stmt)).scalars().all())


async def add_allowed_email(session: AsyncSession, *, actor: User, email: str) -> AllowedEmail:
    """Add an email to the allowlist, audit it, and commit.

    Raises:
        EmailAlreadyAllowed: the email is already allowed.
    """
    existing = await session.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
    if existing is not None:
        raise EmailAlreadyAllowed(f"{email} is already on the allowlist")
    entry = AllowedEmail(email=email, invited_by_id=actor.id)
    session.add(entry)
    await session.flush()
    await record_audit(
        session,
        actor=actor,
        action="allowlist.add",
        target_type="allowed_email",
        target_id=str(entry.id),
        details={"email": email},
    )
    await session.commit()
    await session.refresh(entry)
    return entry


async def remove_allowed_email(
    session: AsyncSession, *, actor: User, allowed_id: uuid.UUID
) -> None:
    """Remove an allowlist entry, audit it, and commit.

    Raises:
        AllowedEmailNotFound: no such entry.
    """
    entry = await session.get(AllowedEmail, allowed_id)
    if entry is None:
        raise AllowedEmailNotFound(f"Allowed email {allowed_id} not found")
    email = entry.email
    entry_id = entry.id
    await session.delete(entry)
    await record_audit(
        session,
        actor=actor,
        action="allowlist.remove",
        target_type="allowed_email",
        target_id=str(entry_id),
        details={"email": email},
    )
    await session.commit()
