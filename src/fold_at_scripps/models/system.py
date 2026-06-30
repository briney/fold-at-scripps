"""Singleton system settings (operational flags)."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, false, func
from sqlalchemy.orm import Mapped, mapped_column

from fold_at_scripps.models.base import Base


class SystemSettings(Base):
    """A single-row table of global operational flags (e.g. maintenance mode)."""

    __tablename__ = "system_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    standard_max_concurrent_runs: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    power_max_concurrent_runs: Mapped[int] = mapped_column(
        Integer, default=12, server_default="12", nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
