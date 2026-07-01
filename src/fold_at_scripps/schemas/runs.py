"""Run response schemas."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from fold_at_scripps.models import RunStatus


class ToolRef(BaseModel):
    """Compact reference to the tool a run used."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    category: str


class ArtifactRead(BaseModel):
    """An output file produced by a run."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    path: str
    size_bytes: int
    content_type: str | None


class RunSummary(BaseModel):
    """Compact run representation for listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool: ToolRef
    status: RunStatus
    created_at: datetime.datetime
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None


class RunRead(RunSummary):
    """Full run representation, including params and artifacts."""

    params: dict[str, Any]
    assigned_gpu_ids: list[int] | None
    wall_time_seconds: float | None
    gpu_seconds: float | None
    error: str | None
    artifacts: list[ArtifactRead]
