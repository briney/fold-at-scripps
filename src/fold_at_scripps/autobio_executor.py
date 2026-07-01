"""An Executor that runs tools via the autobio CLI."""

from __future__ import annotations

import shutil
import subprocess
import time

from fold_at_scripps.executor import ExecutionRequest, ExecutionResult

_ERROR_TAIL = 4000


def _gpu_spec(gpu_ids: list[int]) -> str:
    """Map assigned GPU IDs to autobio's --gpu value ('none' or 'a,b,c')."""
    if not gpu_ids:
        return "none"
    return ",".join(str(gpu_id) for gpu_id in gpu_ids)


class AutobioExecutor:
    """Runs a tool by shelling out to `autobio run` and collecting its outputs."""

    def __init__(self, autobio_bin: str = "autobio") -> None:
        self._bin = autobio_bin

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run the tool; success = exit code 0; move autobio outputs into outputs_dir."""
        workspace = request.outputs_dir.parent / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        cmd = [
            self._bin,
            "run",
            request.tool_name,
            "--config",
            str(request.config_path),
            "--gpu",
            _gpu_spec(request.gpu_ids),
            "--output-dir",
            str(workspace),
            "--format",
            "json",
        ]
        if request.timeout is not None:
            cmd += ["--timeout", str(request.timeout)]

        sub_timeout = None if request.timeout is None else request.timeout + 60
        start = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=sub_timeout)
        except subprocess.TimeoutExpired:
            wall = time.monotonic() - start
            return ExecutionResult(
                succeeded=False,
                wall_time_seconds=wall,
                gpu_seconds=self._gpu_seconds(wall, request.gpu_ids),
                error="autobio run timed out",
            )
        wall = time.monotonic() - start
        gpu_seconds = self._gpu_seconds(wall, request.gpu_ids)

        if proc.returncode != 0:
            error = (proc.stderr or proc.stdout or "autobio run failed")[-_ERROR_TAIL:]
            return ExecutionResult(
                succeeded=False, wall_time_seconds=wall, gpu_seconds=gpu_seconds, error=error
            )

        autobio_outputs = workspace / "outputs"
        if autobio_outputs.is_dir():
            for item in autobio_outputs.iterdir():
                shutil.move(str(item), str(request.outputs_dir / item.name))
        return ExecutionResult(
            succeeded=True, wall_time_seconds=wall, gpu_seconds=gpu_seconds, error=None
        )

    @staticmethod
    def _gpu_seconds(wall: float, gpu_ids: list[int]) -> float | None:
        """GPU-seconds under exclusive allocation: wall time x number of GPUs."""
        return wall * len(gpu_ids) if gpu_ids else None
