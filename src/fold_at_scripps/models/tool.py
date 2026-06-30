"""Tool catalog model — one row per autobio tool version."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, String, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from fold_at_scripps.models.run import Run


class Tool(UUIDPKMixin, TimestampMixin, Base):
    """A specific version of an autobio tool, synced into the catalog."""

    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("name", "version"),)

    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    gpu_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )

    runs: Mapped[list[Run]] = relationship(back_populates="tool")
