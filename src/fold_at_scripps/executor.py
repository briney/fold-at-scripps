"""Execution boundary: the interface a tool runner implements, plus a fake."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ExecutionRequest:
    """Everything an executor needs to run one tool invocation."""

    tool_name: str
    tool_version: str
    image_tag: str | None
    config_path: Path
    outputs_dir: Path
    gpu_ids: list[int]
    timeout: int | None


@dataclass
class ExecutionResult:
    """The outcome of an execution."""

    succeeded: bool
    wall_time_seconds: float
    gpu_seconds: float | None
    error: str | None


class Executor(Protocol):
    """Runs a tool invocation and reports the result."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...


class FakeExecutor:
    """A deterministic executor for tests (no Docker, no GPUs)."""

    def __init__(
        self,
        *,
        succeeded: bool = True,
        error: str | None = None,
        wall_time_seconds: float = 0.01,
        gpu_seconds: float | None = None,
        write_output: bool = True,
    ) -> None:
        self._succeeded = succeeded
        self._error = error
        self._wall_time_seconds = wall_time_seconds
        self._gpu_seconds = gpu_seconds
        self._write_output = write_output

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Optionally write a dummy output file, then return the configured result."""
        if self._write_output:
            (request.outputs_dir / "result.txt").write_text("fake output\n")
        return ExecutionResult(
            succeeded=self._succeeded,
            wall_time_seconds=self._wall_time_seconds,
            gpu_seconds=self._gpu_seconds,
            error=self._error,
        )
