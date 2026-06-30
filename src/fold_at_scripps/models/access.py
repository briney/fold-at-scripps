"""Registration allowlist and password-reset tokens (local-auth support)."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base, UUIDPKMixin


class AllowedEmail(UUIDPKMixin, Base):
    """An email approved (or invited) to register. Gates account creation."""

    __tablename__ = "allowed_emails"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(UUIDPKMixin, Base):
    """A one-time, expiring password-reset token (admin-initiated)."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
