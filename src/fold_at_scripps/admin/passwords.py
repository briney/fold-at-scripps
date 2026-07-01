"""Admin-initiated password reset (token create + redemption)."""

from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.admin.users import get_user
from fold_at_scripps.audit import record_audit
from fold_at_scripps.auth.passwords import hash_password
from fold_at_scripps.models import PasswordResetToken, User

_DEFAULT_TTL = datetime.timedelta(hours=24)


class InvalidResetToken(Exception):
    """Raised when a reset token is unknown, expired, or already used."""


def _hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a reset token."""
    return hashlib.sha256(token.encode()).hexdigest()


async def create_password_reset(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    ttl: datetime.timedelta = _DEFAULT_TTL,
) -> tuple[str, PasswordResetToken]:
    """Create a one-time reset token for a user; return (plaintext_token, row).

    Raises:
        UserNotFound: no such user.
    """
    user = await get_user(session, user_id)
    token = secrets.token_urlsafe(32)
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=datetime.datetime.now(datetime.UTC) + ttl,
    )
    session.add(row)
    await record_audit(
        session,
        actor=actor,
        action="user.password_reset_created",
        target_type="user",
        target_id=str(user.id),
    )
    await session.commit()
    await session.refresh(row)
    return token, row


async def redeem_password_reset(session: AsyncSession, *, token: str, new_password: str) -> User:
    """Redeem a reset token, setting the user's password. One-time use.

    Raises:
        InvalidResetToken: token unknown, expired, or already used.
    """
    row = await session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(token))
    )
    now = datetime.datetime.now(datetime.UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidResetToken("Invalid or expired reset token")
    user = await session.get(User, row.user_id)
    if user is None:  # pragma: no cover - token FK guarantees the user exists
        raise InvalidResetToken("Invalid or expired reset token")
    user.hashed_password = hash_password(new_password)
    row.used_at = now
    await record_audit(
        session,
        actor=None,
        action="user.password_reset_redeemed",
        target_type="user",
        target_id=str(user.id),
    )
    await session.commit()
    await session.refresh(user)
    return user
