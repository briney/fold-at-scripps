"""A ToolSource backed by the autobio CLI (`autobio list` / `autobio info`)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from fold_at_scripps.catalog.sources import ToolRecord, ToolSource


def parse_tool_names(payload: list[dict[str, Any]]) -> list[str]:
    """Extract tool names from `autobio list --format json` output."""
    return [item["name"] for item in payload]


def parse_tool_info(payload: dict[str, Any]) -> ToolRecord:
    """Build a ToolRecord from `autobio info <name> --format json` output."""
    return ToolRecord(
        name=payload["name"],
        version=payload["version"],
        category=payload["category"],
        gpu_count=payload.get("gpu_count", 0),
        default_timeout=payload["default_timeout"],
        supports_batch=payload["supports_batch"],
        description=payload.get("description"),
        image_tag=payload.get("image_tag"),
        input_schema=payload["input_schema"],
    )


class AutobioToolSource:
    """Fetches the catalog by invoking the autobio CLI with JSON output."""

    def __init__(self, autobio_bin: str = "autobio", timeout: int = 120) -> None:
        self._bin = autobio_bin
        self._timeout = timeout

    def _run_json(self, *args: str) -> Any:
        """Run an autobio subcommand with `--format json` and parse stdout."""
        result = subprocess.run(
            [self._bin, *args, "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=self._timeout,
        )
        return json.loads(result.stdout)

    def fetch_tools(self) -> list[ToolRecord]:
        """List tools, then fetch each tool's full info, into ToolRecords."""
        names = parse_tool_names(self._run_json("list"))
        return [parse_tool_info(self._run_json("info", name)) for name in names]


def get_tool_source() -> ToolSource:
    """FastAPI dependency returning the catalog's tool source (overridable in tests)."""
    return AutobioToolSource()
