"""Artifact model — a file produced by a run."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fold_at_scripps.models.base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from fold_at_scripps.models.run import Run


class Artifact(UUIDPKMixin, Base):
    """A single output file produced by a run, indexed for listing and download."""

    __tablename__ = "artifacts"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="artifacts")
