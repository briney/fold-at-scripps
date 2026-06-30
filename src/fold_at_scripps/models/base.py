"""Declarative base, common mixins, and column helpers for ORM models."""

from __future__ import annotations

import datetime
import enum
import uuid

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with a stable constraint-naming convention for Alembic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPKMixin:
    """Mixin adding a client-generated UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Mixin adding server-managed created/updated timestamps."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def str_enum(enum_cls: type[enum.StrEnum]) -> SAEnum:
    """Return a non-native (VARCHAR + CHECK) SQLAlchemy Enum that stores enum values."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=max(len(member.value) for member in enum_cls),
        values_callable=lambda cls: [member.value for member in cls],
    )
