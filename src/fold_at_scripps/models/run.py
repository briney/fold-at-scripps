"""Run model — one submission of a tool by a user."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, TimestampMixin, UUIDPKMixin, str_enum
from fold_at_scripps.models.enums import RunStatus

if TYPE_CHECKING:
    from fold_at_scripps.models.tool import Tool
    from fold_at_scripps.models.user import User


class Run(UUIDPKMixin, TimestampMixin, Base):
    """A single run of a tool: queued, scheduled onto GPUs, executed, recorded."""

    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_user_id_hidden_at", "user_id", "hidden_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), index=True, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus), default=RunStatus.QUEUED, index=True, nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assigned_gpu_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wall_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="runs")
    tool: Mapped[Tool] = relationship(back_populates="runs")
