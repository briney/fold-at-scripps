"""User account model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import UserRole, UserStatus, UserTier

if TYPE_CHECKING:
    from fold_at_scripps.models.run import Run


class User(UUIDPKMixin, TimestampMixin, Base):
    """A user account (local authentication in v1)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        str_enum(UserRole), default=UserRole.USER, nullable=False
    )
    tier: Mapped[UserTier] = mapped_column(
        str_enum(UserTier), default=UserTier.STANDARD, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus), default=UserStatus.PENDING, nullable=False
    )
    max_concurrent_runs_override: Mapped[int | None] = mapped_column(nullable=True)

    runs: Mapped[list[Run]] = relationship(back_populates="user")
