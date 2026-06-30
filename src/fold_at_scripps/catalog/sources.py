"""Tool-source boundary: how the catalog learns about available tools."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel


class ToolRecord(BaseModel):
    """A single tool's metadata as reported by a source (e.g. autobio)."""

    name: str
    version: str
    category: str
    gpu_count: int
    default_timeout: int
    supports_batch: bool
    description: str | None = None
    image_tag: str | None = None
    input_schema: dict[str, Any]


class ToolSource(Protocol):
    """Yields the set of tools currently available from a backend."""

    def fetch_tools(self) -> list[ToolRecord]: ...


class FakeToolSource:
    """An in-memory tool source for tests."""

    def __init__(self, records: list[ToolRecord]) -> None:
        self._records = records

    def fetch_tools(self) -> list[ToolRecord]:
        """Return the configured records."""
        return self._records
