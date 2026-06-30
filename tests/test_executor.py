"""Tests for the executor boundary and its fake."""

from __future__ import annotations

from pathlib import Path

from fold_at_scripps.executor import ExecutionRequest, FakeExecutor


def _request(tmp_path: Path) -> ExecutionRequest:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    return ExecutionRequest(
        tool_name="proteinmpnn",
        tool_version="1.0.0",
        image_tag="proteinmpnn:1.0.0",
        config_path=tmp_path / "config.json",
        outputs_dir=outputs,
        gpu_ids=[0],
        timeout=600,
    )


def test_fake_executor_success_writes_output(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = FakeExecutor().execute(request)
    assert result.succeeded is True
    assert result.error is None
    assert any(request.outputs_dir.iterdir())


def test_fake_executor_failure(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = FakeExecutor(succeeded=False, error="boom", write_output=False).execute(request)
    assert result.succeeded is False
    assert result.error == "boom"
    assert not any(request.outputs_dir.iterdir())
