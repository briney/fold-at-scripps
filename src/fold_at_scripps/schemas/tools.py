"""Catalog (tool) response schemas."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolSummary(BaseModel):
    """Compact tool representation for catalog listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    category: str
    gpu_count: int
    description: str | None
    supports_batch: bool


class ToolRead(ToolSummary):
    """Full tool representation, including the input schema."""

    image_tag: str | None
    default_timeout: int | None
    input_schema: dict[str, Any]
